#!/usr/bin/env bash
# scripts/smoke-passthrough.sh
# Smoke: POST /agent/sleep/stream and assert AgentRouted + RunFinished events.
set -euo pipefail

URL="${ORCHESTRATOR_URL:-http://localhost:8000}/agent/sleep/stream"
TOKEN="${SUPABASE_TEST_TOKEN:-}"
AUTH_ARGS=()
if [[ -n "$TOKEN" ]]; then
  AUTH_ARGS=(-H "Authorization: Bearer $TOKEN")
fi

resp=$(curl -sS -N -X POST "$URL" \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  "${AUTH_ARGS[@]}" \
  -d '{"messages":[{"role":"user","content":"how did I sleep"}],"threadId":"smoke-passthrough"}' \
  --max-time 30)

echo "$resp"

echo "$resp" | grep -q '"type": "AgentRouted"' || { echo "FAIL: no AgentRouted"; exit 1; }
echo "$resp" | grep -q '"primary": "sleep"' || { echo "FAIL: primary != sleep"; exit 1; }
echo "$resp" | grep -q '"type": "RunFinished"' || { echo "FAIL: no RunFinished"; exit 1; }
echo "PASS"
