#!/usr/bin/env bash
# Full-stack end-to-end: send a /chat/stream request, assert a trace tree
# appears in Langfuse with the expected shape.
set -euo pipefail

source .env

# Override any .env values pointing at Docker internal hostnames — this script
# runs from the host, not from inside a container.
LANGFUSE_URL="http://localhost:3100"
ORCH_URL="http://localhost:8000"
PUB="${LANGFUSE_PUBLIC_KEY}"
SEC="${LANGFUSE_SECRET_KEY}"
SESSION="e2e-$(date +%s)"

echo "== 1/3: POST /chat/stream (session=${SESSION}) =="
curl -sf -X POST "${ORCH_URL}/chat/stream" \
    -H 'Content-Type: application/json' \
    -d "{\"threadId\":\"${SESSION}\",\"messages\":[{\"role\":\"user\",\"content\":\"what did I eat yesterday?\"}]}" \
    > /dev/null
echo "ok"

echo "== 2/3: Waiting 10s for span flush =="
sleep 10

echo "== 3/3: Querying Langfuse for trace =="
RESP=$(curl -sf -u "${PUB}:${SEC}" "${LANGFUSE_URL}/api/public/traces?sessionId=${SESSION}")
TRACE_COUNT=$(echo "${RESP}" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("data",[])))')
if [ "${TRACE_COUNT}" -lt "1" ]; then
    echo "FAIL: expected ≥1 trace for session ${SESSION}, got ${TRACE_COUNT}"
    exit 1
fi

TRACE_ID=$(echo "${RESP}" | python3 -c 'import json,sys; print(json.load(sys.stdin)["data"][0]["id"])')
FULL=$(curl -sf -u "${PUB}:${SEC}" "${LANGFUSE_URL}/api/public/traces/${TRACE_ID}")
OBS_COUNT=$(echo "${FULL}" | python3 -c 'import json,sys; print(len(json.load(sys.stdin).get("observations",[])))')

echo "Trace ID: ${TRACE_ID}"
echo "Observations: ${OBS_COUNT}"
if [ "${OBS_COUNT}" -lt "3" ]; then
    echo "FAIL: expected ≥3 observations (root + at least agent + LLM), got ${OBS_COUNT}"
    exit 1
fi

echo "== E2E smoke PASSED =="
echo "View trace at: ${LANGFUSE_URL}/traces/${TRACE_ID}"
