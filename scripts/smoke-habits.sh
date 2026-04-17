#!/usr/bin/env bash
# End-to-end smoke against the live docker stack:
# define → list → check (boolean) → check (quantitative, target met via 2 calls)
# → analyze → archive → re-define same name.
#
# Requires the stack to be running (`docker compose up -d`) and .env configured.
set -euo pipefail

HABITS_URL="${HABITS_AGENT_URL:-http://localhost:8006/}"

rpc() {
  local method="$1"
  local skill="$2"
  local text="$3"
  local params="${4:-\{\}}"
  local rid="smoke-$(date +%s%N)"
  local payload
  payload=$(jq -n --arg m "$method" --arg sk "$skill" --arg t "$text" \
             --argjson p "$params" --arg rid "$rid" '
    {jsonrpc:"2.0", method:$m, id:$rid,
     params:{
       message:{role:"user", messageId:$rid,
                parts:[{kind:"text", text:$t}],
                metadata:{skillId:$sk, params:$p}}}}')
  curl -sS -H "Content-Type: application/json" -d "$payload" "$HABITS_URL"
}

echo "==> 1. agent card"
curl -sS "${HABITS_URL}.well-known/agent.json" \
  | jq '{protocol:.protocolVersion, name:.name, skills:(.skills|length)}'

echo "==> 2. define: meditation daily 20min"
rpc message/send define_habit "медитация 20 минут каждый день" '{}' | jq '.result // .error'

echo "==> 3. list via streak summary"
rpc message/send get_streak_summary "/habits" '{}' | jq '.result // .error'

echo "==> 4. check meditation 10 min"
rpc message/send log_habit_check "/habit meditation 10min" \
  '{"name":"meditation","value":10,"unit":"min","source":"smoke"}' | jq '.result // .error'

echo "==> 5. check meditation 15 min again (target 20 reached: 10+15=25)"
rpc message/send log_habit_check "/habit meditation 15min" \
  '{"name":"meditation","value":15,"unit":"min","source":"smoke"}' | jq '.result // .error'

echo "==> 6. analyze"
rpc message/send analyze_habit "how am I doing" '{"days":7}' | jq '.result // .error'

echo "==> 7. archive"
rpc message/send archive_habit "stop meditation" '{"name":"meditation"}' | jq '.result // .error'

echo "==> 8. re-define (same name should work now)"
rpc message/send define_habit "медитация 20 минут каждый день" '{}' | jq '.result // .error'

echo "==> 9. cleanup"
rpc message/send archive_habit "stop meditation" '{"name":"meditation"}' | jq '.result // .error'

echo "==> SMOKE OK"
