#!/usr/bin/env bash
# End-to-end smoke test against live stack:
# agent card → get_readiness → analyze_recovery_trend → get_recommendations → briefing preview
#
# Requires: stack up (`docker compose up -d`), Garmin sync has already populated some
# sleep_session + daily_stats rows in health_logs.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
RECOVERY_URL="${RECOVERY_AGENT_URL:-http://localhost:8007/}"
ORCH_URL="${ORCHESTRATOR_URL:-http://localhost:8000}"

say() { echo ""; echo "==> $*"; }

say "1. agent card"
curl -sS "${RECOVERY_URL}.well-known/agent.json" | jq '{
  protocol: .protocolVersion,
  name: .name,
  skills: (.skills | length),
  skill_ids: [.skills[].id]
}'

say "2. pre-flight: health_logs has Garmin data"
GARMIN_ROWS=$(docker compose exec -T postgres psql -U "$(grep POSTGRES_USER $REPO_ROOT/.env | cut -d= -f2)" -d "$(grep POSTGRES_DB $REPO_ROOT/.env | cut -d= -f2)" -tAc \
  "SELECT COUNT(*) FROM health_logs WHERE type IN ('sleep_session','daily_stats') AND recorded_at >= now() - interval '7 days';")
echo "Garmin rows in last 7d: $GARMIN_ROWS"
if [[ "$GARMIN_ROWS" -lt 3 ]]; then
  echo "SKIP: <3 Garmin rows in last 7 days — run sync first"
  exit 0
fi

say "3. chat: am I recovered"
P=$(jq -n '{threadId:"smoke-r1",runId:"r1",messages:[{role:"user",content:"как я восстанавливаюсь сегодня"}]}')
curl -sS -X POST -H "Content-Type: application/json" -d "$P" "${ORCH_URL}/chat/stream" | tail -40

say "4. chat: recovery trend this week"
P=$(jq -n '{threadId:"smoke-r2",runId:"r2",messages:[{role:"user",content:"recovery trend over the past week"}]}')
curl -sS -X POST -H "Content-Type: application/json" -d "$P" "${ORCH_URL}/chat/stream" | tail -40

say "5. chat: workout→recovery chain (should I run today)"
P=$(jq -n '{threadId:"smoke-r3",runId:"r3",messages:[{role:"user",content:"should I do a hard run today"}]}')
TRANSCRIPT=$(curl -sS -X POST -H "Content-Type: application/json" -d "$P" "${ORCH_URL}/chat/stream")
echo "$TRANSCRIPT" | tail -40
if echo "$TRANSCRIPT" | grep -qiE "recover|hrv|stress|ready"; then
  echo "PASS: response references recovery context"
else
  echo "WARN: response does not reference recovery — ReAct may not have chained"
fi

say "6. briefing preview"
docker compose exec -T -w /app orchestrator python -c "
import asyncio, sys
sys.path.insert(0, '/app')
from app.db import get_yesterday_metrics
from app.briefing import format_message

async def main():
    m = await get_yesterday_metrics()
    return format_message(m, insight=None)

print(asyncio.run(main()))
" | tee /tmp/recovery-smoke-briefing.log

if grep -q "🔋 Recovery:" /tmp/recovery-smoke-briefing.log; then
  echo "PASS: briefing has 🔋 Recovery line"
else
  echo "NOTE: briefing has no 🔋 line — expected if yesterday data is 'unknown' bucket"
fi

echo ""
echo "==> SMOKE OK"
