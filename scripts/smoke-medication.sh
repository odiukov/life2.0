#!/usr/bin/env bash
# scripts/smoke-medication.sh — e2e sanity for medication agent.
set -euo pipefail

BASE="${MEDICATION_URL:-http://localhost:8008}"

echo "== health =="
curl -fsS "$BASE/health" && echo

echo "== AgentCard =="
curl -fsS "$BASE/.well-known/agent.json" | python3 -m json.tool | head -30
echo

echo "== define via A2A =="
curl -fsS -X POST "$BASE/" -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":"1","method":"message/send","params":{"message":{
    "role":"user",
    "parts":[{"kind":"text","text":"smoke-test-med 50mg daily evening"}],
    "messageId":"smoke-1",
    "metadata":{"skillId":"define_medication","params":{"source":"smoke"}}
  }}
}' | python3 -m json.tool | grep -E '"text"|"state"'
echo

echo "== list_active =="
curl -fsS -X POST "$BASE/" -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":"2","method":"message/send","params":{"message":{
    "role":"user",
    "parts":[{"kind":"text","text":""}],
    "messageId":"smoke-2",
    "metadata":{"skillId":"list_active","params":{}}
  }}
}' | python3 -m json.tool | grep -E '"text"'
echo

echo "== log_taken =="
curl -fsS -X POST "$BASE/" -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":"3","method":"message/send","params":{"message":{
    "role":"user",
    "parts":[{"kind":"text","text":"took smoke-test-med"}],
    "messageId":"smoke-3",
    "metadata":{"skillId":"log_taken","params":{"name":"smoke-test-med","source":"smoke"}}
  }}
}' | python3 -m json.tool | grep -E '"text"'
echo

echo "== archive =="
curl -fsS -X POST "$BASE/" -H 'Content-Type: application/json' -d '{
  "jsonrpc":"2.0","id":"4","method":"message/send","params":{"message":{
    "role":"user",
    "parts":[{"kind":"text","text":"stop smoke-test-med"}],
    "messageId":"smoke-4",
    "metadata":{"skillId":"archive_medication","params":{"name":"smoke-test-med"}}
  }}
}' | python3 -m json.tool | grep -E '"text"'

echo
echo "== DONE =="
