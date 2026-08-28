#!/usr/bin/env bash
# End-to-end durability smoke against the live stack.
#
# 1. Sends a message asking the assistant to remember a number.
# 2. Restarts the orchestrator container.
# 3. Sends a follow-up on the same threadId.
# 4. Asserts the follow-up response contains the number.
#
# Requires: stack up (`docker compose up -d`).
set -euo pipefail

cd "$(dirname "$0")/.."

ORCH_URL="${ORCHESTRATOR_URL:-http://localhost:8000}"
TS=$(date +%s)
THREAD="smoke-checkpoint-$TS"
NUMBER="7421"

say() { echo ""; echo "==> $*"; }

wait_for_orch() {
  for i in $(seq 1 30); do
    if curl -sSf "${ORCH_URL}/health" > /dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  echo "FAIL: orchestrator did not become healthy within 30s"
  exit 1
}

post_chat() {
  local content="$1"
  local payload
  payload=$(jq -n --arg t "$THREAD" --arg c "$content" \
    '{threadId:$t, runId:"r-\(now)", messages:[{role:"user", content:$c}]}')
  curl -sS -X POST -H "Content-Type: application/json" -d "$payload" "${ORCH_URL}/chat/stream"
}

say "1. pre-flight: orchestrator healthy"
wait_for_orch

say "2. first message — tell the assistant to remember a number"
FIRST=$(post_chat "Please remember the number $NUMBER. I will ask you about it in a moment.")
echo "$FIRST" | tail -10

say "3. restart orchestrator (this is the durability test)"
docker compose restart orchestrator
wait_for_orch

say "4. second message on the SAME threadId"
SECOND=$(post_chat "What number did I ask you to remember?")
echo "$SECOND" | tail -20

say "5. assert the response contains $NUMBER"
if echo "$SECOND" | grep -q "$NUMBER"; then
  echo "PASS: orchestrator remembered $NUMBER across a restart"
else
  echo "FAIL: orchestrator did not remember $NUMBER — checkpointer may not be persisting"
  exit 1
fi

echo ""
echo "==> SMOKE OK (thread: $THREAD)"
