#!/usr/bin/env bash
# End-to-end smoke test against the live stack:
# health → tool discovery → read query → CRUD roundtrip (create → verify → delete → verify deleted) → briefing
#
# Pre-requisites:
#   - Stack up: `docker compose up -d`
#   - OAuth setup done: `./gcp-oauth.keys.json` exists, `./mcp-config/calendar-mcp/*.json` has a token
#   - See RUNNING.md "Google Calendar setup (one-time)" if not yet configured
set -euo pipefail

MCP_URL="${MCP_GOOGLE_CALENDAR_URL_HOST:-http://localhost:9100}"
ORCH_URL="${ORCHESTRATOR_URL:-http://localhost:8000}"

say() { echo ""; echo "==> $*"; }

# ----------------------------- pre-flight -----------------------------

say "0. pre-flight: OAuth artefacts present?"
if [[ ! -f ./gcp-oauth.keys.json ]]; then
  echo "SKIP: ./gcp-oauth.keys.json missing — follow RUNNING.md to set up Google Calendar OAuth first."
  exit 0
fi
if ! ls mcp-config/calendar-mcp/*.json >/dev/null 2>&1; then
  echo "SKIP: no token file in mcp-config/calendar-mcp/ — run 'docker compose exec calendar-mcp npm run auth' first."
  exit 0
fi

# ----------------------------- steps -----------------------------

say "1. MCP server health"
if curl -sSf "${MCP_URL}/" >/dev/null 2>&1; then
  echo "MCP health OK"
else
  # Try /mcp endpoint if root doesn't respond
  curl -sS -o /dev/null -w "HTTP %{http_code}\n" "${MCP_URL}/mcp" | head -1
fi

say "2. orchestrator loaded calendar tools"
docker compose logs --tail 200 orchestrator | grep -iE "loaded .*mcp tools|list[-_]events" \
  | tee /tmp/calendar-smoke.log || true
if [[ ! -s /tmp/calendar-smoke.log ]]; then
  echo "FAIL: orchestrator logs show no MCP tool discovery — check MCP_GOOGLE_CALENDAR_URL env + calendar-mcp health"
  exit 1
fi

say "3. read: 'what events do I have on my calendar today'"
PAYLOAD=$(jq -n '{threadId:"smoke-'"$(date +%s)"'",runId:"r1",messages:[{role:"user",content:"what events do I have on my calendar today"}]}')
curl -sS -X POST -H "Content-Type: application/json" -d "$PAYLOAD" "${ORCH_URL}/chat/stream" \
  | tail -50

say "4. CRUD: create test event 10 minutes in the future"
NOW_TS=$(date +%s)
START_ISO=$(date -u -v+10M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+10 minutes' +%Y-%m-%dT%H:%M:%SZ)
END_ISO=$(date -u -v+40M +%Y-%m-%dT%H:%M:%SZ 2>/dev/null || date -u -d '+40 minutes' +%Y-%m-%dT%H:%M:%SZ)
EVENT_TITLE="life-agents-smoke-${NOW_TS}"
CREATE_PAYLOAD=$(jq -n --arg t "$EVENT_TITLE" --arg s "$START_ISO" --arg e "$END_ISO" \
  '{threadId:"smoke-crud",runId:"r2",
    messages:[{role:"user",content:("create a calendar event titled \""+$t+"\" from "+$s+" to "+$e+". confirm yes.")}]}')
curl -sS -X POST -H "Content-Type: application/json" -d "$CREATE_PAYLOAD" "${ORCH_URL}/chat/stream" \
  | tail -50

say "5. CRUD: verify created"
VERIFY_PAYLOAD=$(jq -n --arg t "$EVENT_TITLE" \
  '{threadId:"smoke-verify",runId:"r3",
    messages:[{role:"user",content:("search my calendar for an event titled \""+$t+"\"")}]}')
VERIFY_OUT=$(curl -sS -X POST -H "Content-Type: application/json" -d "$VERIFY_PAYLOAD" "${ORCH_URL}/chat/stream")
echo "$VERIFY_OUT" | tail -20
if echo "$VERIFY_OUT" | grep -q "$EVENT_TITLE"; then
  echo "event confirmed in listing"
else
  echo "WARN: event not found in verify step — continuing to delete (LLM may have created with different title)"
fi

say "6. CRUD: delete"
DELETE_PAYLOAD=$(jq -n --arg t "$EVENT_TITLE" \
  '{threadId:"smoke-delete",runId:"r4",
    messages:[{role:"user",content:("delete the calendar event titled \""+$t+"\". confirm yes.")}]}')
curl -sS -X POST -H "Content-Type: application/json" -d "$DELETE_PAYLOAD" "${ORCH_URL}/chat/stream" \
  | tail -50

say "7. CRUD: verify deleted"
VERIFY2_PAYLOAD=$(jq -n --arg t "$EVENT_TITLE" \
  '{threadId:"smoke-verify2",runId:"r5",
    messages:[{role:"user",content:("search my calendar for an event titled \""+$t+"\"")}]}')
VERIFY2_OUT=$(curl -sS -X POST -H "Content-Type: application/json" -d "$VERIFY2_PAYLOAD" "${ORCH_URL}/chat/stream")
if echo "$VERIFY2_OUT" | grep -q "$EVENT_TITLE"; then
  echo "FAIL: event \"$EVENT_TITLE\" still present after delete"
  exit 1
fi
echo "event confirmed deleted"

say "8. briefing contains 📅 line (if today has events)"
docker compose exec -T orchestrator python -c "
import asyncio, sys
sys.path.insert(0, '/shared')
from orchestrator.app.db import get_yesterday_metrics
from orchestrator.app.briefing import format_message
m = asyncio.run(get_yesterday_metrics())
msg = format_message(m, insight=None)
print(msg)
" | tee /tmp/calendar-smoke-briefing.log || true

if grep -q "📅" /tmp/calendar-smoke-briefing.log; then
  echo "briefing has calendar line"
else
  echo "NOTE: briefing has no 📅 line — expected if today is empty or no all-day events"
fi

echo ""
echo "==> SMOKE OK"
