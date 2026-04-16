#!/usr/bin/env bash
# End-to-end smoke test for agent-body against a running stack.
# Requires: docker compose up (postgres, qdrant, agent-body), .env with POSTGRES_* set.
set -euo pipefail

BODY_URL="${BODY_URL:-http://localhost:8004}"

echo "== AgentCard =="
curl -fsS "$BODY_URL/.well-known/agent.json" | python -c "import json,sys;c=json.load(sys.stdin);print(c['name'], c['protocol_version'], [s['id'] for s in c['skills']])"

echo
echo "== message/send get_latest_body =="
PAYLOAD=$(python - <<'PY'
import json, uuid
print(json.dumps({
  "jsonrpc": "2.0",
  "id": str(uuid.uuid4()),
  "method": "message/send",
  "params": {
    "message": {
      "role": "user",
      "parts": [{"kind": "text", "text": "what's my current weight"}],
      "messageId": str(uuid.uuid4()),
      "metadata": {"skillId": "get_latest_body"},
    }
  }
}))
PY
)

RESPONSE=$(curl -fsS -X POST "$BODY_URL/" -H 'Content-Type: application/json' -d "$PAYLOAD")
echo "$RESPONSE" | python -c "
import json, sys
r = json.load(sys.stdin)
result = r.get('result', {})
state = result.get('status', {}).get('state')
print('state =', state)
for art in result.get('artifacts') or []:
    for p in art.get('parts') or []:
        t = p.get('text') or (p.get('root') or {}).get('text')
        if t:
            print('artifact text:', t[:200])
assert state == 'completed', f'expected completed, got {state}'
"
echo "smoke passed"
