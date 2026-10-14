#!/usr/bin/env bash
# PostToolUse hook: format JS/TS/JSON/MD files with prettier after Edit/Write.
# Uses pnpm exec prettier (3.x) — fails silently if prettier can't process the file.
set -euo pipefail

input=$(cat)
repo_root=$(git -C "$(dirname "$0")" rev-parse --show-toplevel 2>/dev/null || true)
[ -n "$repo_root" ] || exit 0

# Codex sends apply_patch edits in tool_input.command; file tools use file_path.
while IFS= read -r file; do
  [ -n "$file" ] || continue
  case "$file" in
    /*) ;;
    *) file="$repo_root/$file" ;;
  esac
  [ -f "$file" ] || continue
  case "$file" in
    *.ts|*.tsx|*.js|*.jsx|*.mjs|*.cjs|*.json|*.md) ;;
    *) continue ;;
  esac
  case "$file" in
    */node_modules/*|*/.venv/*|*/dist/*|*/build/*|*/.next/*|*/.expo/*|*/.turbo/*|*/coverage/*) continue ;;
  esac
  [ "$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null)" = "$repo_root" ] || continue
  (cd "$repo_root" && pnpm exec prettier --write --log-level=warn "$file" >/dev/null 2>&1) || true
done < <(printf '%s' "$input" | jq -r '
  (.tool_input.file_path // empty),
  ((.tool_input.command // .tool_input.patch // "") | split("\n")[] |
    select(test("^\\*\\*\\* (Add|Update) File: ")) |
    sub("^\\*\\*\\* (Add|Update) File: "; ""))
')
exit 0
