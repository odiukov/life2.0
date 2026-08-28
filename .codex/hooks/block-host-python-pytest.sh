#!/usr/bin/env bash
# PreToolUse hook: block host-Python pytest invocations.
# CLAUDE.md & memory:ops_pytest_venv — host Python 3.14 breaks copilotkit/langchain.
# Allowed: .venv/bin/python -m pytest, .venv/bin/pytest, rtk pytest
set -euo pipefail

input=$(cat)
cmd=$(printf '%s' "$input" | jq -r '.tool_input.command // ""')
[ -z "$cmd" ] && exit 0

# Allow .venv-prefixed or rtk-proxied invocations.
if printf '%s' "$cmd" | grep -qE '(\.venv/bin/|(^|[[:space:]])rtk[[:space:]]+pytest)'; then
  exit 0
fi

# Block: bare/host python invoking pytest
if printf '%s' "$cmd" | grep -qE '(^|[^/A-Za-z0-9_.])(python(3(\.[0-9]+)?)?|/Library/Frameworks/Python\.framework/[^[:space:]]+/python[0-9.]*)[[:space:]]+-m[[:space:]]+pytest'; then
  cat >&2 <<'MSG'
Blocked: host Python invoking pytest.
Use .venv/bin/python -m pytest (CLAUDE.md & memory:ops_pytest_venv).
Host Python 3.14 breaks copilotkit/langchain imports.
MSG
  exit 2
fi

# Block: bare `pytest` / `pytest3`
if printf '%s' "$cmd" | grep -qE '(^|[[:space:]])pytest3?([[:space:]]|$)'; then
  cat >&2 <<'MSG'
Blocked: bare pytest.
Use .venv/bin/python -m pytest instead (memory:ops_pytest_venv).
MSG
  exit 2
fi

exit 0
