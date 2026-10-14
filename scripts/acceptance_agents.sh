#!/usr/bin/env bash
# Run from the repo root against a configured stack with AUTH_MODE=dev.
# Writes synthetic data for one dedicated user; never deletes data or volumes.
set -euo pipefail
API=${API:-http://localhost:8000}
AGENT_HOST=${AGENT_HOST:-http://localhost}
U=44444444-4444-4444-4444-444444444444
pass() { echo "PASS  $*"; }
fail() { echo "FAIL  $*" >&2; exit 1; }
for command in curl jq docker; do command -v "$command" >/dev/null || fail "missing $command"; done
if [[ -f .env ]]; then set -a; source .env; set +a; fi
: "${APP_RW_PASSWORD:?configure APP_RW_PASSWORD in .env or environment}"
: "${POSTGRES_DB:?configure POSTGRES_DB in .env or environment}"
say_to() {
  local reply
  reply=$(curl --fail-with-body -sS -N --max-time 180 \
    -H "X-User-Id: $U" -H 'content-type: application/json' "$API/agent/$1/stream" \
    -d "$(jq -nc --arg t "$2" '{messages:[{role:"user",content:$t}]}')" |
    sed -n 's/^data: //p' | jq -rs '
      if any(.[]; .type == "RunFinished") then
        [.[] | select(.type == "TextMessageContent") | .delta] | join("")
      else error("incomplete SSE stream") end') || fail "$1 HTTP/SSE request failed"
  [[ -n "$reply" && "$reply" != *'Error:'* ]] || fail "$1 empty/error reply: $reply"
  printf '%s\n' "$reply"
}
sql() {
  docker compose exec -T -e PGPASSWORD="$APP_RW_PASSWORD" postgres \
    psql -X -qAt -v ON_ERROR_STOP=1 -h localhost -U app_rw -d "$POSTGRES_DB" \
    -c "BEGIN; SELECT set_config('app.user_id', '$U', true); $1; COMMIT;" | tail -1
}
stored() {
  local label=$1 predicate=$2 result
  result=$(sql "SELECT count(*) FROM health_logs WHERE user_id='$U' AND id != ALL('$EXISTING'::uuid[]) AND ($predicate)")
  [[ "$result" =~ ^[0-9]+$ && "$result" -ge 1 ]] || fail "stored $label ($result)"
  pass "stored $label"
}
# Snapshot IDs: recorded_at may describe yesterday, and health_logs has no created_at.
EXISTING=$(sql "SELECT coalesce(array_agg(id), '{}'::uuid[]) FROM health_logs WHERE user_id='$U'")
[[ "$EXISTING" =~ ^\{[a-f0-9,-]*\}$ ]] || fail 'invalid existing row IDs'
expected_skills() {
  case "$1" in
    sleep) echo 'log_sleep analyze_sleep get_sleep_recommendations' ;;
    workout) echo 'log_workout analyze_workout get_workout_recommendations' ;;
    nutrition) echo 'log_meal analyze_nutrition get_nutrition_recommendations set_body_profile' ;;
    body) echo 'get_latest_body analyze_body_trend' ;;
    mood) echo 'log_mood analyze_mood get_mood_recommendations coach_session' ;;
    habits) echo 'define_habit log_habit_check analyze_habit get_streak_summary archive_habit' ;;
    recovery) echo 'get_readiness analyze_recovery_trend get_recommendations' ;;
    medication) echo 'define_medication log_medication list_active analyze_adherence archive_medication' ;;
    *) fail "unknown agent $1" ;;
  esac
}
for pair in sleep:8001 workout:8002 nutrition:8003 body:8004 mood:8005 habits:8006 recovery:8007 medication:8008; do
  name=${pair%%:*}; port=${pair##*:}
  card=$(curl --fail-with-body -sS --max-time 15 "$AGENT_HOST:$port/.well-known/agent-card.json")
  [[ "$(jq -r .name <<< "$card")" == "$name-agent" ]] || fail "$name card name"
  expected=$(expected_skills "$name" | jq -Rc 'split(" ") | sort')
  actual=$(jq -c '[.skills[].id] | sort' <<< "$card")
  [[ "$actual" == "$expected" ]] || fail "$name skill IDs: expected $expected, got $actual"
  pass "$name card"
done
say_to sleep 'спал с 23:30 до 7' ; pass 'sleep log reply'
say_to workout 'пробежал 5 км за 28 минут'; pass 'workout log reply'
say_to mood 'настроение 6 из 10, устал от работы'; pass 'mood log reply'
say_to habits 'создай привычку meditation: медитация 10 минут каждый день'
say_to habits '/habit meditation'; pass 'habit check reply'
say_to medication 'добавь лекарство vitamin-d: витамин D 2000 МЕ каждое утро'
say_to medication 'принял витамин д'; pass 'medication intake reply'
stored sleep "agent='sleep' AND type='sleep_session' AND (data->>'duration_seconds')::numeric=27000"
stored workout "agent='workout' AND type='activity' AND (data->>'distance_meters')::numeric=5000 AND (data->>'duration_seconds')::numeric=1680"
stored mood "agent='mood' AND type='mood' AND (data->>'mood_score')::numeric=6"
stored habit "agent='habits' AND type='habit' AND data->>'completed'='true' AND EXISTS (SELECT 1 FROM habits h WHERE h.id::text=data->>'habit_id' AND h.name='meditation' AND h.archived_at IS NULL)"
stored medication "agent='medication' AND type='medication_taken' AND EXISTS (SELECT 1 FROM medications m WHERE m.id::text=data->>'medication_id' AND m.archived_at IS NULL AND m.dose LIKE '%2000%')"
analysis() {
  local agent=$1 question=$2 pattern=$3 second=${4:-.} answer
  answer=$(say_to "$agent" "$question")
  printf '\n%s analysis:\n%s\n' "$agent" "$answer"
  [[ "$answer" =~ $pattern ]] || fail "$agent analysis omitted expected fact ($pattern); inspect DEBUG prompt data"
  [[ "$answer" =~ $second ]] || fail "$agent analysis omitted second expected fact ($second)"
  pass "$agent analysis contains expected fact (review answer above)"
}
analysis sleep 'Проанализируй мой сон за неделю, укажи длительность последнего сна.' '7[,.]5|7[^0-9]{0,15}30|23:30'
analysis workout 'Проанализируй тренировки за неделю, укажи дистанцию и время последней пробежки.' '(^|[^0-9])5([^0-9]|$)' '28'
# Fact matches are smoke assertions; manually review the interpretation of those facts.
analysis mood 'Проанализируй настроение за неделю, укажи последнюю оценку.' '6'
analysis habits 'Как идут мои привычки? Укажи meditation и последнюю отметку.' '[Mm]editation|медитац'
analysis medication 'Как я соблюдаю приём лекарств? Назови препарат и дозу последнего приёма.' '2000|[Vv]itamin|витамин'
# Nutrition remains part of the eight-agent real-model acceptance.
answer=$(say_to nutrition 'Проанализируй моё питание за неделю. Чего не хватает для оценки?')
printf '\nnutrition analysis (manual review required):\n%s\n' "$answer"
# No direct recovery/body entries are created: print for manual empty-history/context review.
for agent in recovery body; do
  answer=$(say_to "$agent" 'Проанализируй мои данные за неделю. Чего не хватает для оценки?')
  printf '\n%s analysis (manual review required):\n%s\n' "$agent" "$answer"
done
echo 'Automated checks finished. Review every printed analysis for factual accuracy; nutrition/recovery/body require manual acceptance.'
