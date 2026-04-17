#!/usr/bin/env bash
#
# End-to-end smoke for agent-mood. Requires the full docker-compose stack running.
#
#   ./scripts/redeploy.sh   # rebuild and start everything
#   ./scripts/smoke-mood.sh
#
set -euo pipefail

AGENT_URL="${AGENT_URL:-http://localhost:8005}"

echo "=== 1. Agent card ==="
card=$(curl -sf "$AGENT_URL/.well-known/agent.json")
python3 - <<PY
import json, sys
card = json.loads("""$card""")
assert card["protocolVersion"] == "0.3.0", card["protocolVersion"]
assert card["name"] == "mood-agent"
skill_ids = {s["id"] for s in card["skills"]}
required = {"log_mood", "analyze_mood", "get_recommendations", "coach_session"}
assert required <= skill_ids, skill_ids
print("  card ok:", sorted(skill_ids))
PY

echo "=== 2. log_mood via JSON-RPC ==="
resp=$(curl -sf -X POST "$AGENT_URL/" \
  -H "Content-Type: application/json" \
  -d '{
        "jsonrpc":"2.0","id":"1",
        "method":"message/send",
        "params":{
          "message":{
            "role":"user",
            "parts":[{"kind":"text","text":"чувствую себя уставшим но продуктивным"}],
            "messageId":"m-smoke-1",
            "metadata":{"skillId":"log_mood"}
          }
        }
      }')
echo "$resp" | python3 -c 'import sys, json; d=json.load(sys.stdin); assert "result" in d, d; print("  log_mood ok")'

echo "=== 3. analyze_mood via JSON-RPC ==="
resp=$(curl -sf -X POST "$AGENT_URL/" \
  -H "Content-Type: application/json" \
  -d '{
        "jsonrpc":"2.0","id":"2",
        "method":"message/send",
        "params":{
          "message":{
            "role":"user",
            "parts":[{"kind":"text","text":"analyze my mood this week"}],
            "messageId":"m-smoke-2",
            "metadata":{"skillId":"analyze_mood"}
          }
        }
      }')
echo "$resp" | python3 -c 'import sys, json; d=json.load(sys.stdin); assert "result" in d, d; print("  analyze_mood ok")'

echo "=== 4. Row written to health_logs ==="
docker compose exec -T postgres psql -U "${POSTGRES_USER:-health}" -d "${POSTGRES_DB:-health}" -tAc \
  "SELECT COUNT(*) FROM health_logs WHERE type = 'mood';" | tee /tmp/mood-count.txt
count=$(cat /tmp/mood-count.txt | tr -d '[:space:]')
if [ "$count" = "0" ]; then
  echo "  FAIL: no mood rows found"
  exit 1
fi
echo "  mood rows in DB: $count"

echo ""
echo "✓ smoke-mood OK"
