#!/usr/bin/env bash
# PostToolUse hook: format JS/TS/JSON/MD files with prettier after Edit/Write.
# Uses pnpm exec prettier (3.x) — fails silently if prettier can't process the file.
set -euo pipefail

input=$(cat)
file=$(printf '%s' "$input" | jq -r '.tool_input.file_path // ""')
[ -z "$file" ] && exit 0
[ -f "$file" ] || exit 0

case "$file" in
  *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.md) ;;
  *) exit 0 ;;
esac

case "$file" in
  */node_modules/*|*/.venv/*|*/dist/*|*/build/*|*/.next/*|*/.expo/*|*/.turbo/*|*/coverage/*) exit 0 ;;
esac

repo_root=$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null || echo "")
[ -z "$repo_root" ] && exit 0

cd "$repo_root"
pnpm exec prettier --write --log-level=warn "$file" >/dev/null 2>&1 || true
exit 0
