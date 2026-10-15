#!/usr/bin/env bash
# Run each domain agent through a dedicated task on a dev-auth stack.
set -euo pipefail
cd "$(dirname "$0")/.."
API=${API:-http://localhost:8000}
AGENT_HOST=${AGENT_HOST:-http://localhost}
USER_ID=${ACCEPTANCE_USER_ID:-44444444-4444-4444-4444-444444444444}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
for tool in curl jq; do command -v "$tool" >/dev/null || { echo "FAIL missing_tool name=$tool"; exit 1; }; done
curl -fsS --max-time 30 -H "X-User-Id: $USER_ID" "$API/household" -o "$WORK/household.json"
jq -e '.id != null' "$WORK/household.json" >/dev/null

agents=(sleep workout nutrition body mood habits recovery medication kitchen finance calendar home)
ports=(8001 8002 8003 8004 8005 8006 8007 8008 8009 8011 8012 8013)
for index in "${!agents[@]}"; do
  agent=${agents[$index]}
  port=${ports[$index]}
  curl -fsS --max-time 15 "$AGENT_HOST:$port/.well-known/agent-card.json" -o "$WORK/card.json"
  jq -e --arg agent "$agent" '.name == ($agent + "-agent") and (.skills | length > 0)' "$WORK/card.json" >/dev/null
  task_id=$(curl -fsS --max-time 30 -H "X-User-Id: $USER_ID" -H 'Content-Type: application/json' \
    -d "$(jq -nc --arg agent "$agent" '{lead_agent:$agent}')" "$API/tasks" | jq -er '.id')
  curl -fsS -N --max-time 180 -H "X-User-Id: $USER_ID" \
    -F 'text=Summarize the available information in your domain.' \
    -F 'timezone=UTC' "$API/tasks/$task_id/messages" -o "$WORK/stream.sse"
  sed -n 's/^data: //p' "$WORK/stream.sse" | jq -es '
    any(.[]; .type == "RunFinished")
    and any(.[]; .type == "TextMessageContent")
    and all(.[]; .type != "RunError")
  ' >/dev/null
  echo "PASS agent_task name=$agent id=$task_id"
done
