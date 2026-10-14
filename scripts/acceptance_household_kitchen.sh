#!/usr/bin/env bash
# Run against a new, disposable Compose project with AUTH_MODE=dev.
# See RUNNING.md for the isolated-stack setup. Never delete an existing volume.
set -euo pipefail

cd "$(dirname "$0")/.."
API=${API:-http://localhost:8000}
COMPOSE_PROJECT=${ACCEPTANCE_COMPOSE_PROJECT:?Set ACCEPTANCE_COMPOSE_PROJECT to a disposable Compose project}
ENV_FILE=${ACCEPTANCE_ENV_FILE:-.env}
LLM_AVAILABLE=${ACCEPTANCE_LLM_AVAILABLE:-1}
A=11111111-1111-1111-1111-111111111111
B=22222222-2222-2222-2222-222222222222
C=33333333-3333-3333-3333-333333333333
DIGEST_NOW=${ACCEPTANCE_DIGEST_NOW:-2099-01-01T23:00:00+00:00}
DIGEST_DATE=${DIGEST_NOW:0:10}
EXPIRY_DATE=$(date -u -j -f '%Y-%m-%d' -v+1d "$DIGEST_DATE" '+%Y-%m-%d' 2>/dev/null || date -u -d "$DIGEST_DATE + 1 day" '+%Y-%m-%d')
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
failures=0
skips=0

for tool in curl jq docker; do
  command -v "$tool" >/dev/null || { echo "FAIL  missing $tool"; exit 1; }
done
[[ -r "$ENV_FILE" ]] || { echo "FAIL  missing config file"; exit 1; }
env_value() { sed -n "s/^$1=//p" "$ENV_FILE" | tail -1; }
AUTH_MODE=$(env_value AUTH_MODE)
POSTGRES_USER=$(env_value POSTGRES_USER)
POSTGRES_DB=$(env_value POSTGRES_DB)
APP_RW_PASSWORD=$(env_value APP_RW_PASSWORD)
[[ ${AUTH_MODE:-} == dev ]] || { echo "FAIL  AUTH_MODE must be dev"; exit 1; }
[[ -n "$POSTGRES_USER" && -n "$POSTGRES_DB" && -n "$APP_RW_PASSWORD" ]] || { echo "FAIL  incomplete database config"; exit 1; }

compose() { docker compose --env-file "$ENV_FILE" -p "$COMPOSE_PROJECT" "$@"; }
pass() { echo "PASS  $1"; }
fail() { echo "FAIL  $1"; failures=$((failures + 1)); }
skip() { echo "SKIP  $1"; skips=$((skips + 1)); }
equal() {
  local label=$1 actual=$2 expected=$3
  if [[ "$actual" == "$expected" ]]; then pass "$label"; return 0; fi
  fail "$label (expected $expected, got $actual)"
  return 1
}
api() {
  local who=$1 method=$2 path=$3 payload=${4:-}
  local args=(-sS --max-time 120 -o "$WORK/response" -w '%{http_code}'
    -H "X-User-Id: $who" -H 'content-type: application/json' -X "$method")
  [[ -z "$payload" ]] || args+=(-d "$payload")
  HTTP_STATUS=$(curl "${args[@]}" "$API$path") || { fail "request $method $path"; return 1; }
  if [[ "$HTTP_STATUS" != 2* ]]; then
    fail "$method $path returned HTTP $HTTP_STATUS"
    return 1
  fi
}
json() { jq -er "$@" "$WORK/response"; }
sql_owner() { compose exec -T postgres psql -X -v ON_ERROR_STOP=1 -U "$POSTGRES_USER" -d "$POSTGRES_DB" -tAc "$1"; }
sql_rw() {
  compose exec -T -e "PGPASSWORD=$APP_RW_PASSWORD" postgres \
    psql -X -v ON_ERROR_STOP=1 -h localhost -U app_rw -d "$POSTGRES_DB" -tAc "$1"
}
seed_batch() {
  local household=$1 author=$2 name=$3 expires=$4
  sql_owner "INSERT INTO kitchen_batches (household_id,name,display_name,category,quantity,unit,location,status,added_at,added_by,expires_on,expiry_source,next_check_on,source) VALUES ('$household','$name','$name','other',1,'pcs','fridge','active',now(),'$author','$expires','explicit','$expires','text')" >/dev/null
}
sse_text() { sed -n 's/^data: //p' "$1" | jq -sr '[.[] | select(.type == "TextMessageContent") | .delta] | join("")'; }
relay_tool_text() {
  compose exec -T orchestrator python - "$1" <<'PY'
import asyncio
import json
import os
import sys

from langchain_core.messages import AIMessage, ToolMessage
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver


async def main() -> None:
    async with AsyncPostgresSaver.from_conn_string(os.environ["POSTGRES_DSN"]) as saver:
        saved = await saver.aget_tuple({"configurable": {"thread_id": sys.argv[1]}})
    messages = [] if saved is None else saved.checkpoint["channel_values"].get("messages", [])
    ids = {
        call["id"]
        for message in messages
        if isinstance(message, AIMessage)
        for call in message.tool_calls
        if call["name"] == "ask_kitchen_agent"
    }
    replies = [
        message.content
        for message in messages
        if isinstance(message, ToolMessage) and message.tool_call_id in ids
    ]
    print(json.dumps(replies[-1] if replies else None))


asyncio.run(main())
PY
}

# A reused project would invalidate all counts and isolation claims.
if [[ $(sql_owner 'SELECT count(*) FROM household_members' 2>/dev/null) != 0 ]] || \
   [[ $(sql_owner 'SELECT count(*) FROM kitchen_batches' 2>/dev/null) != 0 ]] || \
   [[ $(sql_owner 'SELECT count(*) FROM notifications' 2>/dev/null) != 0 ]]; then
  echo "FAIL  acceptance database is not clean"
  exit 1
fi
pass 'clean database (zero members, batches and notifications)'

if api "$A" GET /household && [[ $(json '.my_role' 2>/dev/null) == owner ]]; then
  pass 'A owns a household'
else
  fail 'A owns a household'; exit 1
fi
HOUSEHOLD_A=$(json '.id')
if api "$A" PATCH /household '{"timezone":"UTC","digest_time":"18:00"}' && \
   [[ $(json '.timezone') == UTC ]]; then pass 'stable UTC household timezone';
else fail 'stable UTC household timezone'; exit 1; fi
if api "$A" POST /household/invites; then
  CODE=$(json '.code' 2>/dev/null || true)
  [[ "$CODE" =~ ^[A-Z0-9]{4}-[A-Z0-9]{4}$ ]] && pass 'invite created' || { fail 'invite created'; exit 1; }
else exit 1; fi
api "$B" GET /household || exit 1
HOUSEHOLD_B=$(json '.id')

if [[ "$LLM_AVAILABLE" == 1 ]]; then
  for phrase in 'купил кефир' 'купил творог'; do
    payload=$(jq -nc --arg text "$phrase" '{messages:[{role:"user",content:$text}]}')
    if api "$B" POST /agent/kitchen/stream "$payload"; then
      cp "$WORK/response" "$WORK/direct.sse"
      response=$(sse_text "$WORK/direct.sse")
      [[ "$response" == *'Записал'* ]] && pass 'direct kitchen A2A purchase' || fail 'direct kitchen A2A purchase'
    fi
  done
else
  skip 'direct kitchen A2A purchases (no real LLM configured)'
  seed_batch "$HOUSEHOLD_B" "$B" acceptance_kefir "$EXPIRY_DATE"
  seed_batch "$HOUSEHOLD_B" "$B" acceptance_curd "$EXPIRY_DATE"
fi
if api "$B" POST /household/join/preview "$(jq -nc --arg code "$CODE" '{code:$code}')"; then
  equal 'preview moves two active items' "$(json '.items_to_move')" 2 || true
fi
api "$B" POST /household/join "$(jq -nc --arg code "$CODE" '{code:$code}')" || exit 1
if api "$A" GET /kitchen/inventory; then
  equal 'A sees B items after join' "$(json '.items | length')" 2 || true
fi

if [[ "$LLM_AVAILABLE" == 1 ]]; then
  THREAD=$(uuidgen | tr '[:upper:]' '[:lower:]')
  payload=$(jq -nc --arg thread "$THREAD" '{threadId:$thread,messages:[{role:"user",content:"купил молоко и 2 кг курицы"}]}')
  if api "$B" POST /chat/stream "$payload"; then
    cp "$WORK/response" "$WORK/chat.sse"
    chat_text=$(sse_text "$WORK/chat.sse")
    if [[ "$chat_text" == 'Записал:'* ]]; then pass 'chat kitchen response starts with recorded confirmation';
    else fail 'chat kitchen response starts with recorded confirmation'; fi
    tool_json=$(relay_tool_text "$THREAD" 2>"$WORK/relay.err" || true)
    tool_text=$(jq -nr --argjson value "${tool_json:-null}" '$value // empty' 2>/dev/null || true)
    if [[ -n "$tool_text" && "$tool_text" == "$chat_text" ]]; then
      pass 'orchestrator relays kitchen tool response verbatim'
    else
      fail 'orchestrator relays kitchen tool response verbatim'
    fi
    if api "$A" GET /kitchen/inventory; then equal 'four items after chat' "$(json '.items | length')" 4 || true; fi
  fi
else
  skip 'chat routing, four-item result and verbatim relay (no real LLM configured)'
  seed_batch "$HOUSEHOLD_A" "$B" acceptance_chicken "$EXPIRY_DATE"
fi

if api "$A" GET /kitchen/inventory; then
  CHICKEN=$(json '.items[] | select(.name | test("куриц|acceptance_chicken")) | .id' 2>/dev/null | head -1 || true)
  if [[ -n "$CHICKEN" ]] && api "$A" POST "/kitchen/items/$CHICKEN/action" '{"action":"consumed"}'; then
    GROUP=$(json '.group_id')
    if api "$A" POST "/kitchen/undo/$GROUP" && api "$A" GET /kitchen/inventory; then
      equal 'action and undo restore chicken' "$(json --arg id "$CHICKEN" '[.items[] | select(.id == $id)] | length')" 1 || true
    fi
  else fail 'chicken available for action and undo'; fi
fi

if command -v say >/dev/null && command -v afconvert >/dev/null; then
  if { say -v Milena 'купил хлеб' -o "$WORK/voice.aiff" 2>/dev/null || say 'купил хлеб' -o "$WORK/voice.aiff"; } && \
     afconvert -f WAVE -d LEI16@16000 "$WORK/voice.aiff" "$WORK/voice.wav"; then
    status=$(curl -sS --max-time 180 -o "$WORK/voice.json" -w '%{http_code}' -H "X-User-Id: $A" \
      -F "audio=@$WORK/voice.wav;type=audio/wav" -F language=ru "$API/voice/transcribe" || true)
    if [[ "$status" == 200 ]] && jq -e '.text | length > 0' "$WORK/voice.json" >/dev/null; then
      pass 'spoken audio returns non-empty transcript'
    else fail "spoken audio returns non-empty transcript (HTTP $status)"; fi
  else fail 'speech fixture generation'; fi
else skip 'spoken audio (say/afconvert unavailable)'; fi
head -c 2500000 /dev/zero > "$WORK/big.wav"
status=$(curl -sS --max-time 30 -o "$WORK/too-big.json" -w '%{http_code}' -H "X-User-Id: $A" \
  -F "audio=@$WORK/big.wav;type=audio/wav" "$API/voice/transcribe" || true)
equal 'oversized audio is rejected' "$status" 413 || true

# A future clock prevents the live scheduler from racing this deterministic run.
# Move earlier test purchases outside the due window so the named fixture is
# guaranteed to be rendered even if the chat path added many batches.
sql_owner "UPDATE kitchen_batches SET expires_on = ('$DIGEST_DATE'::date + interval '30 days')::date, next_check_on = ('$DIGEST_DATE'::date + interval '30 days')::date WHERE household_id = '$HOUSEHOLD_A' AND status = 'active'" >/dev/null
seed_batch "$HOUSEHOLD_A" "$A" acceptance_expiry_fixture "$EXPIRY_DATE"
first=$(compose exec -T agent-kitchen python -m kitchen.run_digest --now "$DIGEST_NOW" 2>"$WORK/digest-first.err" || true)
second=$(compose exec -T agent-kitchen python -m kitchen.run_digest --now "$DIGEST_NOW" 2>"$WORK/digest-second.err" || true)
equal 'first digest claims one household' "$first" 'digests sent: 1' || true
equal 'second digest is idempotent' "$second" 'digests sent: 0' || true
for who in "$A" "$B"; do
  if api "$who" GET /notifications; then
    equal 'one kitchen digest in member inbox' "$(json '[.items[] | select(.kind == "kitchen.digest")] | length')" 1 || true
    equal 'digest names the seeded expiring item' "$(json --arg fixture acceptance_expiry_fixture '[.items[] | select(.kind == "kitchen.digest") | .body | contains($fixture)] | any')" true || true
    equal 'digest marks the seeded item for tomorrow' "$(json '[.items[] | select(.kind == "kitchen.digest") | .body | test("завтра|tomorrow")] | any')" true || true
  fi
done

api "$C" GET /household || exit 1
if [[ $(json '.id') != "$HOUSEHOLD_A" ]]; then pass 'C belongs to a separate household';
else fail 'C belongs to a separate household'; fi
equal 'C sees only own membership' "$(json '.members | length')" 1 || true
if api "$C" GET /kitchen/inventory; then equal 'C sees no kitchen items' "$(json '.items | length')" 0 || true; fi
if api "$C" GET /notifications; then equal 'C sees no notifications' "$(json '.items | length')" 0 || true; fi
status=$(curl -sS --max-time 30 -o "$WORK/redeemed.json" -w '%{http_code}' \
  -H "X-User-Id: $C" -H 'content-type: application/json' \
  -d "$(jq -nc --arg code "$CODE" '{code:$code}')" "$API/household/join/preview" || true)
equal 'C cannot preview redeemed invite' "$status" 404 || true
raw=$(sql_rw "BEGIN; SELECT set_config('app.user_id', '$C', true); SELECT count(*) FROM kitchen_batches; ROLLBACK" 2>"$WORK/sql.err" | tail -2 | head -1 || true)
equal 'app_rw RLS hides batches from C' "$raw" 0 || true
raw=$(sql_rw "BEGIN; SELECT set_config('app.user_id', '$C', true); SELECT count(*) FROM notifications; ROLLBACK" 2>"$WORK/sql.err" | tail -2 | head -1 || true)
equal 'app_rw RLS hides notifications from C' "$raw" 0 || true
raw=$(sql_rw "BEGIN; SELECT set_config('app.user_id', '$C', true); SELECT count(*) FROM household_invites; ROLLBACK" 2>"$WORK/sql.err" | tail -2 | head -1 || true)
equal 'app_rw RLS hides invites from C' "$raw" 0 || true

echo "Acceptance: $failures failed, $skips skipped"
[[ "$failures" == 0 && "$skips" == 0 ]]
