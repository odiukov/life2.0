#!/usr/bin/env bash
# End-to-end task chat acceptance on an isolated AUTH_MODE=dev stack.
# Optional: HA_ENTITY, PAYONEER_PDF, VIHEALTH_PDF, LANGFUSE_PUBLIC_KEY/SECRET_KEY.
set -euo pipefail
cd "$(dirname "$0")/.."
API=${API:-http://localhost:8000}
A=55555555-5555-5555-5555-555555555555
B=66666666-6666-6666-6666-666666666666
work=$(mktemp -d)
trap 'rm -rf "$work"' EXIT
pass() { echo "PASS code=$1${2:+ $2}"; }
skip() { echo "SKIP code=$1"; }
fail() { echo "FAIL code=$1${2:+ $2}" >&2; exit 1; }
for tool in curl jq docker; do command -v "$tool" >/dev/null || fail missing_tool "name=$tool"; done
json() { command jq "$@" 2>/dev/null; }
if [[ -f .env ]]; then set -a; source .env; set +a; fi
[[ -n "${APP_RW_PASSWORD:-}" && -n "${POSTGRES_DB:-}" ]] || fail database_not_configured

api() { # user method path [json]; writes body to a private temporary file
  local user=$1 method=$2 path=$3 data=${4:-}
  if [[ -n "$data" ]]; then
    curl -s -o "$work/body.json" -w '%{http_code}' --max-time 30 -X "$method" \
      -H "X-User-Id: $user" -H 'content-type: application/json' -d "$data" "$API$path" || true
  else
    curl -s -o "$work/body.json" -w '%{http_code}' --max-time 30 -X "$method" \
      -H "X-User-Id: $user" "$API$path" || true
  fi
}
check_status() { # expected user method path [json]
  local expected=$1; shift
  local actual
  actual=$(api "$@")
  [[ "$actual" == "$expected" ]] || fail http_status "status=$actual expected=$expected"
}
say() { # user task text [extra curl -F args...]; stores parsed events privately
  local user=$1 task=$2 message=$3; shift 3
  local status
  status=$(curl -s -o "$work/events.sse" -w '%{http_code}' --max-time 240 -N \
    -H "X-User-Id: $user" -F "text=$message" -F "timezone=Europe/Kyiv" "$@" \
    "$API/tasks/$task/messages" || true)
  [[ "$status" == 200 ]] || fail chat_http "status=$status"
  sed -n 's/^data: //p' "$work/events.sse" | json -s '.' > "$work/events.json" || fail invalid_sse
  json -e 'any(.[]; .type=="RunFinished") and all(.[]; .type!="RunError")' \
    "$work/events.json" >/dev/null || fail chat_run
}
sql_count() { # user query; returns a count only
  local user=$1 query=$2
  docker compose exec -T -e PGPASSWORD="$APP_RW_PASSWORD" postgres \
    psql -X -qAt -v ON_ERROR_STOP=1 -h localhost -U app_rw -d "$POSTGRES_DB" -c \
    "BEGIN; SELECT set_config('app.user_id', '$user', true); $query; COMMIT;" \
    2>/dev/null | awk '/^[0-9]+$/ { value=$0 } END { print value }'
}

check_status 200 "$A" GET /dashboard/summary
[[ $(json -r '.unavailable | length' "$work/body.json") == 0 ]] || fail cards_unavailable
pass dashboard
check_status 200 "$A" GET /agents
[[ $(json '[.agents[] | select(.online)] | length' "$work/body.json") -ge 12 ]] || fail agents_offline
pass agents "count=12"

check_status 201 "$A" POST /tasks '{}'
task=$(json -er '.id' "$work/body.json") || fail task_id_missing
say "$A" "$task" 'Ask both the sleep and nutrition agents: how did I sleep last night, and what should I eat for dinner based on that sleep?'
json -e 'any(.[]; .type=="AgentRouted") and any(.[]; .type=="AgentConsulted" and (.peers | length)>0) and any(.[]; .type=="TextMessageContent")' \
  "$work/events.json" >/dev/null || fail routing_events
primary=$(json -r '[.[] | select(.type=="AgentRouted")][0].primary' "$work/events.json")
pass chat "id=$task primary=$primary"
check_status 200 "$A" GET "/tasks/$task"
[[ $(json '.messages | length' "$work/body.json") == 2 ]] || fail transcript_count
pass restore "id=$task count=2"

for method in GET DELETE PATCH; do
  status=$(api "$B" "$method" "/tasks/$task" '{}')
  [[ "$status" == 404 ]] || fail task_isolation "method=$method status=$status"
done
[[ $(sql_count "$B" "SELECT count(*) FROM chat_messages WHERE task_id = '$task'") == 0 ]] \
  || fail transcript_rls
for table in checkpoints checkpoint_blobs checkpoint_writes; do
  [[ $(sql_count "$B" "SELECT count(*) FROM $table WHERE thread_id = '$A:$task'") == 0 ]] \
    || fail checkpoint_rls "name=$table"
done
pass task_isolation "id=$task"

check_status 200 "$A" PATCH "/tasks/$task" '{"lead_agent":"nutrition"}'
say "$A" "$task" 'а сколько там белка?'
[[ $(json -r '[.[] | select(.type=="AgentRouted")][0].primary' "$work/events.json") == nutrition ]] \
  || fail lead_routing
pass lead_agent "name=nutrition"

if [[ -n "${HA_ENTITY:-}" ]]; then
  check_status 200 "$A" GET /household
  check_status 201 "$A" POST /tasks '{"lead_agent":"home"}'
  home_task=$(json -er '.id' "$work/body.json") || fail home_task_id_missing
  say "$A" "$home_task" "выключи $HA_ENTITY"
  action=$(json -r '[.[] | select(.type=="ActionProposed")][0].actionId // empty' "$work/events.json")
  [[ -n "$action" ]] || fail action_card_missing
  check_status 200 "$A" POST "/tasks/$home_task/actions/$action" '{"decision":"confirm"}'
  [[ $(json -r .status "$work/body.json") == applied ]] || fail action_not_applied
  check_status 200 "$A" POST "/tasks/$home_task/actions/$action" '{"decision":"confirm"}'
  [[ $(json -r .status "$work/body.json") == applied ]] || fail action_not_idempotent
  say "$A" "$home_task" "включи $HA_ENTITY"
  action=$(json -r '[.[] | select(.type=="ActionProposed")][0].actionId // empty' "$work/events.json")
  [[ -n "$action" ]] || fail second_action_card_missing
  say "$A" "$home_task" 'да'
  [[ $(json -r '[.[] | select(.type=="ActionResolved")][0].status' "$work/events.json") == applied ]] \
    || fail typed_confirmation
  check_status 204 "$A" DELETE "/tasks/$home_task"
  pass home_confirmation "id=$home_task"
else
  skip home_confirmation
fi

if [[ -n "${PAYONEER_PDF:-}" ]]; then
  [[ -f "$PAYONEER_PDF" ]] || fail payoneer_file_missing
  say "$A" "$task" '' -F "attachments=@$PAYONEER_PDF;type=application/pdf"
  [[ $(json -r '[.[] | select(.type=="AgentRouted")][0].primary' "$work/events.json") == finance ]] \
    || fail payoneer_route
  pass payoneer_import
else
  skip payoneer_import
fi
if [[ -n "${VIHEALTH_PDF:-}" ]]; then
  [[ -f "$VIHEALTH_PDF" ]] || fail vihealth_file_missing
  check_status 200 "$A" PATCH "/tasks/$task" '{"lead_agent":"body"}'
  say "$A" "$task" '' -F "attachments=@$VIHEALTH_PDF;type=application/pdf"
  [[ $(json -r '[.[] | select(.type=="AgentRouted")][0].primary' "$work/events.json") == body ]] \
    || fail vihealth_route
  pass vihealth_import
else
  skip vihealth_import
fi

if [[ -n "${LANGFUSE_PUBLIC_KEY:-}" && -n "${LANGFUSE_SECRET_KEY:-}" ]]; then
  sleep 10
  trace_count=$(curl -s -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    "${LANGFUSE_URL:-http://localhost:3100}/api/public/traces?sessionId=$task" \
    | json '.data | length') || fail trace_query
  [[ "$trace_count" -ge 1 ]] || fail trace_missing
  pass trace "count=$trace_count"
else
  skip trace
fi

check_status 204 "$A" DELETE "/tasks/$task"
check_status 404 "$A" GET "/tasks/$task"
for table in chat_messages pending_actions; do
  [[ $(sql_count "$A" "SELECT count(*) FROM $table WHERE task_id = '$task'") == 0 ]] \
    || fail close_rows "name=$table"
done
for table in checkpoints checkpoint_blobs checkpoint_writes; do
  [[ $(sql_count "$A" "SELECT count(*) FROM $table WHERE thread_id = '$A:$task'") == 0 ]] \
    || fail close_checkpoints "name=$table"
done
pass close "id=$task"
echo 'ALL PASS'
