# Drop Claude-CLI Provider and OAuth Refresh Hack — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Remove the Claude-CLI LLM provider and every piece of machinery (Keychain export, `.env.auth`, launchd periodic restart) that exists to keep its OAuth token fresh. Leave the stack running on the already-configured `LLM_PROVIDER=openrouter`.

**Architecture:** Pure removal. No code replaces what's deleted. The `shared/shared/llm.py` factory loses one branch; `docker-compose.yml` drops an `env_file` entry and four pairs of bind mounts; two scripts and a launchd plist disappear.

**Tech Stack:** Python 3.13, LangChain (`BaseChatModel` factory), Docker Compose, macOS launchd.

**Spec:** `docs/superpowers/specs/2026-04-17-drop-claude-cli-auth-design.md`

## File Structure

| File | Action |
|---|---|
| `~/Library/LaunchAgents/com.life-agents.refresh-auth.plist` | Unload + delete (outside repo) |
| `logs/refresh-auth.log` | Delete (untracked) |
| `shared/shared/chat_claude_cli.py` | Delete |
| `shared/shared/llm.py` | Modify (drop branch + import) |
| `tests/test_chat_claude_cli.py` | Delete |
| `tests/test_llm.py` | Modify (drop parametrize row + one test + import) |
| `docker-compose.yml` | Modify (drop `.env.auth` from 6 services; drop `~/.claude*` mounts from 4 services) |
| `scripts/export-auth.sh` | Delete |
| `scripts/refresh-auth.sh` | Delete |
| `scripts/redeploy.sh` | Modify (drop one line) |
| `.env.auth` | Delete (untracked) |
| `.env.example` | Modify (drop claude-cli from comments) |
| `RUNNING.md` | Modify (drop two claude-cli references) |
| `~/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/project_life_agents.md` | Modify (update wrapper-v2 + auth sections) |

---

## Task 1: Remove launchd refresh job

**Files:**
- Delete: `~/Library/LaunchAgents/com.life-agents.refresh-auth.plist`
- Delete: `logs/refresh-auth.log`

- [ ] **Step 1: Verify the job is currently loaded**

Run: `launchctl list | grep life-agents`
Expected: one line containing `com.life-agents.refresh-auth`.

- [ ] **Step 2: Unload the job**

Run: `launchctl unload ~/Library/LaunchAgents/com.life-agents.refresh-auth.plist`
Expected: no output.

- [ ] **Step 3: Delete the plist**

Run: `rm ~/Library/LaunchAgents/com.life-agents.refresh-auth.plist`

- [ ] **Step 4: Delete the log file**

Run: `rm -f logs/refresh-auth.log`
(The `logs/` directory can stay; other services may write there.)

- [ ] **Step 5: Verify the job is gone**

Run: `launchctl list | grep life-agents || echo OK`
Expected: `OK`.

Run: `ls ~/Library/LaunchAgents/ | grep life-agents || echo OK`
Expected: `OK`.

(No commit — all out-of-repo actions.)

---

## Task 2: Remove claude-cli provider from code

**Files:**
- Modify: `tests/test_llm.py`
- Delete: `tests/test_chat_claude_cli.py`
- Modify: `shared/shared/llm.py`
- Delete: `shared/shared/chat_claude_cli.py`

- [ ] **Step 1: Baseline — run the full test suite**

Run: `pytest -q`
Expected: all tests pass. Note the number for comparison at step 7.

- [ ] **Step 2: Edit `tests/test_llm.py`**

Open `tests/test_llm.py`.

Remove this import line (currently line 11):
```python
from shared.chat_claude_cli import ChatClaudeCLI
```

Remove the entire `test_claude_cli_branch` function (currently starts around line 85):
```python
def test_claude_cli_branch(monkeypatch):
    monkeypatch.setenv("LLM_PROVIDER", "claude-cli")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "oauth-token")
    llm = build_llm()
    assert isinstance(llm, ChatClaudeCLI)
```
(Delete the whole function including any blank line that separated it from the next test.)

In the missing-key parametrize table (around line 114), remove this row:
```python
        ("claude-cli", "ANTHROPIC_API_KEY"),
```

- [ ] **Step 3: Delete `tests/test_chat_claude_cli.py`**

Run: `rm tests/test_chat_claude_cli.py`

- [ ] **Step 4: Edit `shared/shared/llm.py`**

Open `shared/shared/llm.py`.

In the module docstring (lines 1-23), make two edits:

Replace:
```
    LLM_PROVIDER — one of: anthropic | openrouter | gemini | groq | ollama | claude-cli
                   (default: openrouter).
```
with:
```
    LLM_PROVIDER — one of: anthropic | openrouter | gemini | groq | ollama
                   (default: openrouter).
```

Replace the "Required key per provider" block:
```
    anthropic   — ANTHROPIC_API_KEY
    openrouter  — OPENROUTER_API_KEY
    gemini      — GEMINI_API_KEY
    groq        — GROQ_API_KEY
    ollama      — (none; OLLAMA_HOST optional, defaults to http://localhost:11434)
    claude-cli  — ANTHROPIC_API_KEY  (OAuth token from scripts/export-auth.sh)
```
with:
```
    anthropic   — ANTHROPIC_API_KEY
    openrouter  — OPENROUTER_API_KEY
    gemini      — GEMINI_API_KEY
    groq        — GROQ_API_KEY
    ollama      — (none; OLLAMA_HOST optional, defaults to http://localhost:11434)
```

Remove the import (line 36):
```python
from .chat_claude_cli import ChatClaudeCLI
```

Remove the `"claude-cli"` entry from `_DEFAULT_MODELS` (line 45):
```python
    "claude-cli": "claude-sonnet-4-6",
```

Remove the dispatch branch (lines 67-68):
```python
    if provider == "claude-cli":
        return _build_claude_cli(model)
```

Remove the `_build_claude_cli` function (lines 123-125):
```python
def _build_claude_cli(model: str) -> BaseChatModel:
    _require("ANTHROPIC_API_KEY")
    return ChatClaudeCLI(model=model)
```

- [ ] **Step 5: Delete `shared/shared/chat_claude_cli.py`**

Run: `rm shared/shared/chat_claude_cli.py`

- [ ] **Step 6: Run the full test suite**

Run: `pytest -q`
Expected: all tests pass. Count should be lower than step 1 by at least 2 (`test_claude_cli_branch` removed + one parametrize row removed) plus however many tests were in `test_chat_claude_cli.py`. No new failures.

- [ ] **Step 7: Verify no stale references in code**

Run: `grep -rn 'claude-cli\|chat_claude_cli\|ChatClaudeCLI' shared/ tests/ orchestrator/ agents/ sync_service/ telegram_bot/ copilotkit-runtime/ agui-frontend/ 2>/dev/null || echo OK`
Expected: `OK` (or zero hits).

- [ ] **Step 8: Commit**

```bash
git add shared/shared/llm.py shared/shared/chat_claude_cli.py tests/test_llm.py tests/test_chat_claude_cli.py
git commit -m "refactor(llm): drop claude-cli provider"
```

---

## Task 3: Remove .env.auth plumbing from docker-compose.yml

**Files:**
- Modify: `docker-compose.yml`

The current file has six services that reference `.env.auth` in their `env_file`: `agent-sleep`, `agent-workout`, `agent-nutrition`, `agent-body`, `orchestrator`, `telegram-bot`. Four of the agent services also bind-mount `~/.claude` and `~/.claude.json`.

- [ ] **Step 1: Remove `.env.auth` from every `env_file` list**

For each of the six services above, change:
```yaml
    env_file:
      - .env
      - .env.auth
```
to:
```yaml
    env_file:
      - .env
```

There are six occurrences. Use your editor's find-and-replace on the single line `      - .env.auth` → delete all six.

Verify:

Run: `grep -n '.env.auth' docker-compose.yml || echo OK`
Expected: `OK`.

- [ ] **Step 2: Remove `~/.claude` bind mounts from the four agent services**

For `agent-sleep`, `agent-workout`, `agent-nutrition`, and `agent-body`, delete this block:
```yaml
    volumes:
      - ~/.claude:/root/.claude:ro
      - ~/.claude.json:/root/.claude.json:ro
```

None of these services have any other volumes, so the entire `volumes:` block (3 lines each, 4 services = 12 lines) goes away. If an agent has other volumes added later they'll need adding back — right now there are none.

Verify:

Run: `grep -n '~/.claude' docker-compose.yml || echo OK`
Expected: `OK`.

- [ ] **Step 3: Quick compose syntax check**

Run: `docker compose config -q`
Expected: exit code 0, no output. (Confirms YAML + compose schema still valid.)

- [ ] **Step 4: Commit**

```bash
git add docker-compose.yml
git commit -m "chore(compose): drop .env.auth env_file and claude keychain mounts"
```

---

## Task 4: Delete auth scripts and `.env.auth`

**Files:**
- Delete: `scripts/export-auth.sh`
- Delete: `scripts/refresh-auth.sh`
- Modify: `scripts/redeploy.sh`
- Delete: `.env.auth`

- [ ] **Step 1: Edit `scripts/redeploy.sh`**

Open `scripts/redeploy.sh`. Remove the line (currently line 13):
```bash
./scripts/export-auth.sh
```
Also remove any blank line that was separating it from surrounding code. The final file should look like:
```bash
#!/usr/bin/env bash
# Rebuild images and restart services. `docker compose up -d` alone does NOT
# rebuild when source changes — use this after editing code inside a service.
#
# Usage:
#   scripts/redeploy.sh                      # rebuild + restart everything
#   scripts/redeploy.sh orchestrator         # rebuild + restart one service
#   scripts/redeploy.sh agent-body telegram-bot
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose up -d --build "$@"
docker compose ps
```

- [ ] **Step 2: Delete the two scripts**

Run: `rm scripts/export-auth.sh scripts/refresh-auth.sh`

- [ ] **Step 3: Delete `.env.auth`**

Run: `rm -f .env.auth`

- [ ] **Step 4: Sanity check**

Run: `ls scripts/ | grep -E 'export-auth|refresh-auth' || echo OK`
Expected: `OK`.

Run: `ls .env.auth 2>/dev/null || echo OK`
Expected: `OK`.

Run: `bash -n scripts/redeploy.sh && echo OK`
Expected: `OK` (syntax valid).

- [ ] **Step 5: Commit**

```bash
git add scripts/redeploy.sh scripts/export-auth.sh scripts/refresh-auth.sh
git commit -m "chore(scripts): delete export-auth/refresh-auth, drop call from redeploy"
```

---

## Task 5: Clean docs and `.env.example`

**Files:**
- Modify: `.env.example`
- Modify: `RUNNING.md`

- [ ] **Step 1: Edit `.env.example`**

Open `.env.example`. Change the provider-list comment (line 19):
```
# One of: anthropic | openrouter | gemini | groq | ollama | claude-cli
```
to:
```
# One of: anthropic | openrouter | gemini | groq | ollama
```

Delete the trailing claude-cli block (currently lines 31-33):
```
# claude-cli: ANTHROPIC_API_KEY is populated by scripts/export-auth.sh
# (OAuth token from macOS Keychain). Token expires ~8h.
```
(Delete these two comment lines; the file ends there now, so the new last line is `# OLLAMA_HOST=...`.)

Verify:

Run: `grep -n 'claude-cli\|Keychain\|export-auth' .env.example || echo OK`
Expected: `OK`.

- [ ] **Step 2: Edit `RUNNING.md`**

Open `RUNNING.md`.

Find the provider list line (around line 23) that mentions `claude-cli` and drop `claude-cli`. For example, change:
```
`groq`, `ollama`, `claude-cli`. Default is `openrouter` with a free model. Set the
```
to:
```
`groq`, `ollama`. Default is `openrouter` with a free model. Set the
```

Find the `**Claude CLI (subscription):**` bullet (around line 29) and delete the entire bullet (all its lines, including any indented continuation lines). If the bullet is part of a list, fix the surrounding punctuation/formatting so the list still reads cleanly.

Verify:

Run: `grep -n 'claude-cli\|export-auth' RUNNING.md || echo OK`
Expected: `OK`.

- [ ] **Step 3: Commit**

```bash
git add .env.example RUNNING.md
git commit -m "docs: drop claude-cli from env example and RUNNING.md"
```

---

## Task 6: Update project memory

**Files:**
- Modify: `~/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/project_life_agents.md`

The memory file has two stale references that should be updated so future sessions don't recreate the hack.

- [ ] **Step 1: Read the current memory**

Open `~/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/project_life_agents.md`.

- [ ] **Step 2: Rewrite the "Auth" bullet under "Key non-obvious decisions"**

Find the bullet that currently reads:
```
- **Auth:** Claude OAuth tokens live in macOS Keychain ("Claude Code-credentials"), NOT in ~/.claude.json. Must run `scripts/export-auth.sh` before `docker compose up`. Token expires ~every 8h. Container uses `claude --print --bare` + `ANTHROPIC_API_KEY` env var.
```

Replace with:
```
- **Auth:** Stack runs on `LLM_PROVIDER=openrouter` by default (or any of the other five supported providers — see `shared/shared/llm.py`). The Claude-CLI / macOS-Keychain / `.env.auth` / `refresh-auth.sh` pathway was removed 2026-04-17 — do not recreate it.
```

- [ ] **Step 3: Update the "LLM provider wrapper v2" section**

In the same file, find the "LLM provider wrapper v2 ✅ merged 2026-04-15" header. Update:

a) The provider list line:
```
Six providers: `anthropic`, `openrouter` (default, model `qwen/qwen3-coder-480b-a35b-instruct:free`), `gemini`, `groq`, `ollama`, `claude-cli`.
```
Change to:
```
Five providers: `anthropic`, `openrouter` (default), `gemini`, `groq`, `ollama`. Claude-CLI removed 2026-04-17.
```

b) Delete the `ChatClaudeCLI.bind_tools` decision bullet that reads approximately:
```
- `ChatClaudeCLI.bind_tools` raises a clear `NotImplementedError` directing users to tool-capable providers. So **orchestrator (LangGraph ReAct) cannot use claude-cli**; sub-agents (one-shot) can.
```
(This whole bullet goes away since `ChatClaudeCLI` no longer exists.)

c) In the Ops paragraph, change:
```
`scripts/export-auth.sh` is now optional (only needed for `LLM_PROVIDER=claude-cli`).
```
to:
```
`scripts/export-auth.sh` was removed (2026-04-17) along with the rest of the claude-cli pathway.
```

- [ ] **Step 4: Verify**

Run: `grep -n 'claude-cli\|export-auth\|ChatClaudeCLI' ~/.claude/projects/-Users-oleksandr-Documents-life-agents/memory/project_life_agents.md`
Expected: only historical references that mention the removal (e.g. "removed 2026-04-17"). No references to them as current infra.

(Memory lives outside the repo — no commit needed.)

---

## Task 7: Smoke test the stack without `.env.auth`

**Files:** none (verification only).

- [ ] **Step 1: Bring the stack down clean**

Run: `docker compose down`
Expected: all containers removed.

- [ ] **Step 2: Full rebuild + up**

Run: `scripts/redeploy.sh`
Expected: build finishes, `docker compose ps` prints the final table, every service is either `running (healthy)` or `running` (the few without healthchecks: `postgres` is healthy, `migrate` is `exited (0)`, `telegram-bot` / `agui-frontend` / `copilotkit-runtime` / `orchestrator` just `running`).

- [ ] **Step 3: Confirm compose is not chasing `.env.auth`**

Run: `docker compose config 2>&1 | grep -i 'env.auth' || echo OK`
Expected: `OK`.

- [ ] **Step 4: Smoke the orchestrator chat endpoint**

Run:
```bash
curl -sN -X POST http://localhost:8000/chat/stream \
  -H 'content-type: application/json' \
  -d '{"message":"ping"}' | head -c 4096
```
Expected: a stream of AG-UI events including at least one `TextMessageContent` line with non-empty `delta`. If curl exits with a stream of events, the round-trip works.

- [ ] **Step 5: Final repo hygiene check**

Run: `grep -rn 'claude-cli\|chat_claude_cli\|ChatClaudeCLI\|export-auth\|refresh-auth\|\.env\.auth' --exclude-dir=.git --exclude-dir=docs --exclude-dir=node_modules . 2>/dev/null || echo OK`
Expected: `OK`. (Docs are excluded because historical specs/plans under `docs/superpowers/` retain references by design.)

- [ ] **Step 6: Done — nothing to commit**

This task is verification only. All repo-affecting commits have already landed in tasks 2, 3, 4, 5.
