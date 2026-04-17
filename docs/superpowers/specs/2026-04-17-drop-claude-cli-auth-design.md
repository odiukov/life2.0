# Drop Claude-CLI Provider and OAuth Refresh Hack

**Date:** 2026-04-17
**Status:** design

## Context

The stack currently supports `LLM_PROVIDER=claude-cli`, which runs the Claude CLI as a subprocess inside each agent container using an OAuth token exported from the macOS Keychain. The token expires every ~8 hours, so the setup requires:

1. `scripts/export-auth.sh` — reads Keychain, writes `.env.auth` with `ANTHROPIC_API_KEY`.
2. `scripts/refresh-auth.sh` — re-runs `export-auth.sh` and restarts the three agent containers.
3. `~/Library/LaunchAgents/com.life-agents.refresh-auth.plist` — loaded launchd job, `StartInterval=14400` (every 4h).
4. `docker-compose.yml` — every agent + orchestrator + telegram-bot loads `.env.auth` via `env_file`; all four agent services bind-mount `~/.claude` and `~/.claude.json`.

Meanwhile, production config already uses `LLM_PROVIDER=openrouter` with model `openai/gpt-4o-mini`. The orchestrator has *never* been able to use `claude-cli` (LangGraph ReAct needs tools; `ChatClaudeCLI.bind_tools` raises `NotImplementedError`). The refresh job runs every 4h and restarts agent containers that don't use the token anyway.

Cost of keeping it: ongoing operational surface (Keychain dependency, launchd job, container restart cycle), macOS-only, and a reverse-engineered OAuth path that Anthropic can break at any time.

Trade-off accepted: lose Claude-quality generation in sub-agents. User has confirmed current sub-agent prompts (simple log/analyze/recommend over health logs) don't need it; Groq / OpenRouter is sufficient.

## Goal

Remove the Claude-CLI provider and every piece of machinery that exists to keep its OAuth token fresh. The stack must run from a clean clone with only `.env` (provider API keys) — no Keychain access, no `.env.auth`, no launchd job, no periodic container restarts.

## Non-goals

- Changing the active provider/model (stays `openrouter` / `openai/gpt-4o-mini` — user switches freely via `LLM_PROVIDER`).
- Touching the `sk-ant-oat` OAuth branch inside `_build_anthropic` (separate code path, no-op for real API keys, doesn't require refresh machinery).
- Rewriting historical spec/plan documents — they describe state at a point in time and should not rot.

## Changes

### docker-compose.yml
- Remove `- .env.auth` from `env_file` lists of: `agent-sleep`, `agent-workout`, `agent-nutrition`, `agent-body`, `orchestrator`, `telegram-bot`.
- Remove `volumes:` entries `~/.claude:/root/.claude:ro` and `~/.claude.json:/root/.claude.json:ro` from all four agent services.

### Scripts
- Delete `scripts/export-auth.sh`.
- Delete `scripts/refresh-auth.sh`.
- Edit `scripts/redeploy.sh`: remove line `./scripts/export-auth.sh`. Keep the rest (`docker compose up -d --build "$@"` + `docker compose ps`).

### launchd
- `launchctl unload ~/Library/LaunchAgents/com.life-agents.refresh-auth.plist`.
- Delete `~/Library/LaunchAgents/com.life-agents.refresh-auth.plist`.
- Delete `logs/refresh-auth.log` (`logs/` is untracked, per user note).

### Code
- Delete `shared/shared/chat_claude_cli.py`.
- Edit `shared/shared/llm.py`:
  - Remove `from .chat_claude_cli import ChatClaudeCLI`.
  - Remove `"claude-cli"` entry from `_DEFAULT_MODELS`.
  - Remove the `if provider == "claude-cli": return _build_claude_cli(model)` branch.
  - Delete `_build_claude_cli` function.
  - Update module docstring: drop `claude-cli` from the `LLM_PROVIDER` list and from the "Required key per provider" block.
- Delete `tests/test_chat_claude_cli.py`.
- Edit `tests/test_llm.py`:
  - Remove `from shared.chat_claude_cli import ChatClaudeCLI` import.
  - Remove `test_claude_cli_branch`.
  - Remove `("claude-cli", "ANTHROPIC_API_KEY")` row from the missing-key parametrize table.
- `tests/conftest.py`: no claude-cli references found — no change.
- `scripts/smoke-llm.sh`: no claude references found — no change.

### Env / docs
- Delete `.env.auth` from disk (already git-ignored per `.gitignore`).
- Edit `.env.example`:
  - Comment listing providers: remove `claude-cli`.
  - Delete the trailing block `# claude-cli: ANTHROPIC_API_KEY is populated by scripts/export-auth.sh …`.
- Edit `RUNNING.md`:
  - Line 23 (provider list): remove `claude-cli`.
  - Line 29 block (`**Claude CLI (subscription):** …`): delete entire bullet.

### Memory
- Update `~/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/project_life_agents.md`:
  - "LLM provider wrapper v2" section: drop `claude-cli` from the provider list, delete the "So orchestrator cannot use claude-cli" decision line, note `export-auth.sh` is gone.
  - "Key non-obvious decisions" → "Auth" bullet: rewrite to reflect that Keychain auth is no longer used.

## Out of scope (decided)

- Keeping `ChatClaudeCLI` as dead code for later quality comparisons — rejected; git history preserves it.
- Archiving scripts into `scripts/archive/` — rejected; same reason.

## Risks

1. **Test regression.** `pytest` currently exercises six providers. After removal, the `tests/test_llm.py` parametrize table and branch test must still pass for the remaining five.
2. **Forgotten consumer.** A small chance a helper script or Dockerfile references `~/.claude` mount or `.env.auth`. Grep already ran clean for `export-auth|chat_claude_cli|claude-cli|ChatClaudeCLI` — remaining hits are only historical specs/plans (left alone) and the files being edited/deleted here.
3. **Stack boot after removal.** First `scripts/redeploy.sh` without `export-auth.sh` must succeed end-to-end. Verification: `docker compose ps` all healthy, then smoke via `curl -N -X POST http://localhost:8000/chat/stream -d '…'` to confirm orchestrator → agent round-trip works.

## Rollout order

1. Unload + delete launchd plist (stops scheduled restarts).
2. Delete code (`chat_claude_cli.py`, `llm.py` branch, tests); run `pytest`.
3. Edit `docker-compose.yml` + `scripts/redeploy.sh`; delete scripts `export-auth.sh` / `refresh-auth.sh`.
4. Edit `.env.example` + `RUNNING.md`; delete `.env.auth` file.
5. Update memory notes.
6. `scripts/redeploy.sh` full stack; verify health and smoke the chat endpoint.
7. Commit.

## Verification

- `pytest` green after step 2.
- `launchctl list | grep life-agents` → no output after step 1.
- `docker compose ps` → all services healthy after step 6.
- `curl -sN -X POST http://localhost:8000/chat/stream -H 'content-type: application/json' -d '{"message":"how am i doing today"}'` → receives AG-UI `TextMessageContent` deltas.
- `grep -r 'claude-cli\|export-auth\|chat_claude_cli\|ChatClaudeCLI' --exclude-dir=docs --exclude-dir=.git .` → no matches (docs kept as history).
