#!/usr/bin/env bash
# Smoke test: Langfuse stack is up, OTLP ingest works, trace visible via API.
set -euo pipefail

source .env

LANGFUSE_URL="${LANGFUSE_URL:-http://localhost:3100}"
PUB="${LANGFUSE_PUBLIC_KEY}"
SEC="${LANGFUSE_SECRET_KEY}"
AUTH=$(printf '%s:%s' "$PUB" "$SEC" | base64)

echo "== 1/4: Waiting for langfuse-web health =="
for i in $(seq 1 60); do
    if curl -sf "${LANGFUSE_URL}/api/public/health" >/dev/null 2>&1; then
        echo "ok"
        break
    fi
    sleep 2
    if [ "$i" = "60" ]; then
        echo "FAIL: langfuse-web not healthy after 120s"
        exit 1
    fi
done

echo "== 2/4: Sending a test OTLP span =="
TRACE_ID=$(python3 -c 'import secrets; print(secrets.token_hex(16))')
SPAN_ID=$(python3 -c 'import secrets; print(secrets.token_hex(8))')
NOW_NS=$(python3 -c 'import time; print(int(time.time()*1e9))')
END_NS=$((NOW_NS + 1000000))

PAYLOAD=$(cat <<EOF
{
  "resourceSpans": [{
    "resource": {"attributes": [{"key": "service.name", "value": {"stringValue": "smoke-test"}}]},
    "scopeSpans": [{
      "scope": {"name": "smoke"},
      "spans": [{
        "traceId": "${TRACE_ID}",
        "spanId": "${SPAN_ID}",
        "name": "smoke-test-span",
        "startTimeUnixNano": "${NOW_NS}",
        "endTimeUnixNano": "${END_NS}",
        "kind": 1,
        "attributes": [
          {"key": "langfuse.user.id", "value": {"stringValue": "smoke-test"}}
        ]
      }]
    }]
  }]
}
EOF
)

curl -sf -X POST "${LANGFUSE_URL}/api/public/otel/v1/traces" \
    -H "Authorization: Basic ${AUTH}" \
    -H "Content-Type: application/json" \
    -d "${PAYLOAD}" >/dev/null
echo "ok"

echo "== 3/4: Waiting for trace to appear (up to 15s) =="
for i in $(seq 1 15); do
    COUNT=$(curl -sf -u "${PUB}:${SEC}" \
        "${LANGFUSE_URL}/api/public/traces?userId=smoke-test" \
        | python3 -c 'import json,sys; d=json.load(sys.stdin); print(len(d.get("data",[])))')
    if [ "${COUNT}" -gt "0" ]; then
        echo "ok — trace visible"
        break
    fi
    sleep 1
    if [ "$i" = "15" ]; then
        echo "FAIL: trace not visible after 15s"
        exit 1
    fi
done

echo "== 4/4: Langfuse smoke test PASSED =="
