---
name: smoke
description: Run a smoke test from scripts/smoke-*.sh against the running docker-compose stack, after verifying the relevant services are healthy and surfacing known-quirk preconditions. Use when the user runs /smoke <domain> or asks to smoke-test a specific subsystem.
disable-model-invocation: true
---

# smoke

Run one of the `scripts/smoke-*.sh` end-to-end smoke tests with preflight checks.

## Usage

`/smoke <domain>` where `<domain>` matches a script name (e.g. `mood`, `body`, `calendar`, `langfuse`, `telemetry-e2e`, `vector-memory-live`, `multi-user`).

If invoked without an argument, list the available scripts (`ls scripts/smoke-*.sh`) and ask the user to pick one.

## Steps

### 1. Resolve the script

Always discover scripts at runtime — the set evolves:

```bash
ls scripts/smoke-*.sh | sed 's|.*smoke-||;s|\.sh$||'
```

Match the user's `<domain>` to one of the printed names. If the user typed something close (typo, abbreviation), ask before guessing. If nothing matches, list the options and stop.

### 2. Stack health preflight

```bash
docker compose ps --format json | jq -r '.[] | "\(.Service)\t\(.Status)\t\(.Health // "—")"'
```

Required healthy services depend on the smoke target. Conservative default: `postgres`, `qdrant`, `orchestrator`, and the agent matching the domain (e.g. `agent-mood` for `/smoke mood`). If anything is unhealthy, **stop** and tell the user to run `docker compose up -d --build` (or `--force-recreate` if env changed) first.

### 3. Surface known quirks before running

| Smoke target         | Quirk                                                                                                                                                               |
| -------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `langfuse`           | `ENCRYPTION_KEY` must be exactly 64 hex chars. If recently rotated, full `--force-recreate` of the langfuse stack required.                                         |
| `calendar`           | Calendar-mcp restart must be paired with orchestrator restart or the tool list goes stale (memory:ops_docker_and_migrations). Verify both were brought up together. |
| `mood`               | Mood coach is hard-locked to Groq via `MOOD_COACH_PROVIDER`. If `GROQ_API_KEY` is missing, this smoke fails with a confusing 500. Check `.env` first.               |
| `telemetry-e2e`      | Requires `init_telemetry()` called as the first import-time statement in every agent's `main.py`. If recently refactored, spans may be missing.                     |
| `multi-user`         | Dev-mode auth hacks may interfere (memory:project_multi_user_auth). Confirm `DEV_AUTH_BYPASS` env value.                                                            |
| `vector-memory-live` | Hits real Qdrant — destroys collection state. Don't run if other dev work is in flight.                                                                             |
| `body-agent`         | HealthKit aggregator must write `agent='sleep'` in health_logs (memory:healthkit_aggregator_agent_column). Confirm fix is present.                                  |

If any quirk applies and isn't satisfied, **ask** before running.

### 4. Run

```bash
bash scripts/smoke-<resolved-name>.sh
```

Don't suppress output — the user wants to see what happens. Stream stdout/stderr.

### 5. Report

If the script exits 0: confirm with one line and quote the last few lines of output.

If non-zero: identify the failing assertion, cross-reference with the quirks table, and propose the next step. Common failure → fix:

| Failure pattern                        | Likely cause                                                   |
| -------------------------------------- | -------------------------------------------------------------- |
| `connection refused :8000`             | orchestrator not running — `docker compose up -d orchestrator` |
| `connection refused :800[1-8]`         | the targeted agent isn't up — check `docker compose ps`        |
| `500 Internal Server Error` from agent | check `docker compose logs agent-<name> --tail=50`             |
| `column "agent" does not exist`        | migration 0002 likely not applied (memory)                     |
| `KeyError: 'GROQ_API_KEY'`             | mood-only — set in `.env`, recreate orchestrator + agent-mood  |
| `qdrant connection timeout`            | `qdrant` not healthy — `docker compose restart qdrant`         |

## Things that bite

- Smoke scripts use `set -euo pipefail` — they fail on the first failed `curl` and don't always print a useful message. Re-run with `bash -x scripts/smoke-<name>.sh` if the failure is opaque.
- LLM env changes need `--force-recreate`, not just `restart` (per AGENTS.md docker section).
- `AGENT_URL` env override at the top of each smoke script can be used to point at a worktree-deployed stack on a different port. Mention this if the user has multiple stacks.
