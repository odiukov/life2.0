# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Python tests
```bash
# Always use .venv Python — host Python 3.14 breaks langchain imports
.venv/bin/python -m pytest tests/                          # All tests
.venv/bin/python -m pytest tests/test_briefing.py          # Single file
.venv/bin/python -m pytest -k "alert" -v                   # Pattern match
```

### TypeScript / monorepo
```bash
pnpm install                  # Install all workspace packages
turbo build                   # Build all packages
turbo test                    # Run all TS tests
turbo lint                    # ESLint (note: ESLINT_USE_FLAT_CONFIG=false is set in package.json)
turbo typecheck               # tsc --noEmit across workspaces
pnpm format                   # Prettier
```

### Mobile
```bash
pnpm ios       # expo run:ios
pnpm android   # expo run:android
```

### Docker
```bash
docker compose up --build -d          # Build + start all 14 services
docker compose ps                     # Check health
docker compose logs -f orchestrator   # Follow a service
# LLM env changes need --force-recreate, not just restart
docker compose up --force-recreate orchestrator
```

### Smoke tests (require running stack)
```bash
bash scripts/smoke-llm.sh
bash scripts/smoke-mood.sh
bash scripts/smoke-telemetry-e2e.sh
# etc. — ~20 scripts in scripts/
```

### Database migrations
```bash
# Migrations run automatically on docker compose up via the migrate service
# Add new migration: supabase/migrations/<timestamp>_description.sql
# Migration 0002 must be applied manually (see ops_docker_and_migrations memory)
```

## Architecture

### Service map
```
Frontend:   React Native (apps/mobile)
                │
Orchestrator (:8000) — LangGraph ReAct agent, manages conversation state in PostgreSQL,
                       serves /chat/stream SSE to the mobile app, calls peer agents via A2A SDK
                │
8 Peer Agents (:8001–:8008) — sleep, workout, nutrition, body, mood, habits, recovery, medication
                               Each is a FastAPI + A2A SDK server with 3–4 domain skills
                │
Sync Service (:8080) — polls Garmin & Yazio on schedule, triggers briefing;
                │
Data: PostgreSQL (health_logs, tasks, LangGraph checkpoints) + Qdrant (vector memory)
Observability: self-hosted Langfuse v3 stack (:3100), OTEL via Traceloop SDK
```

### Key patterns

**Agent structure** — every peer agent follows the same layout:
```
agents/<name>/app/
  main.py       # FastAPI + A2A request handler
  executor.py   # Skill routing + LLM call
  skills.py     # AgentCard skill definitions
  prompt.py     # Domain prompt builders
```

**health_logs table** is the universal sink. Dedup key is `(source, type, recorded_at)` — not an upsert, so duplicates are blocked on insert. Every agent uses `agent='sleep'|'workout'|...` when reading; the aggregator agent column must always be set when writing (see healthkit_aggregator_agent_column memory).

**A2A flow**: orchestrator calls peer agents over HTTP using `google-a2a` SDK. Each peer skill receives an A2A Message, runs its LLM prompt, persists results, and streams artifacts back. Peer artifact fetching (for cross-domain context) lives in `shared/peer.py`.

**LangGraph checkpointing**: conversation state is stored per `thread_id` in PostgreSQL via `AsyncPostgresSaver`. Mobile app currently loses `thread_id` on refresh (ephemeral session design).

**Shared Python library**: `shared/` is installed editable (`pip install -e shared/`) into every Python service. Add cross-service utilities here (LLM factory, DB helpers, A2A client cache, vector ops, telemetry init).

**LLM factory** (`shared/llm.py`): all services get their LLM via `LLM_PROVIDER` env var (anthropic | openrouter | gemini | groq | ollama). Mood coach is hard-locked to Groq (`MOOD_COACH_PROVIDER`); it never falls back to paid providers.

**Telemetry**: call `init_telemetry("service-name")` as the first line of every `main.py`. Three consent modes: `full` (dev), `metadata` (token counts only), `consented` (per-user opt-in via `telemetry_consent` table).

### Directory layout
```
agents/           8 peer agents
orchestrator/     LangGraph orchestrator + all specialized modules
sync_service/     Garmin/Yazio poller
apps/
  mobile/         React Native (Expo 54) — HealthKit, share extension, offline SQLite
packages/
  api-client/     OpenAPI-generated TypeScript client (shared by web + mobile)
  i18n/           Russian + English strings
  ui/             Shared React components
shared/           Python shared library (asyncpg, LLM factory, A2A, Qdrant, telemetry)
supabase/migrations/ PostgreSQL schema (Supabase CLI format)
tests/            100+ pytest files; conftest.py seeds LLM env placeholders + TEST_USER_ID
scripts/          ~20 smoke test shell scripts
```

### Integration quirks
- **Yazio**: v18 API has 3 distinct entry shapes; `insert_rows` behaves as UPSERT; sleep query uses "most recent" window, not yesterday.
- **Google Calendar**: direct REST calls (`orchestrator/app/google_calendar_api.py`) with per-user OAuth tokens from the vault — no MCP server in the path.
- **Langfuse `ENCRYPTION_KEY`**: must be exactly 64 hex chars (`openssl rand -hex 32`).
- **A2A client cache**: cleared between tests via `clear_caches()`; don't share across test cases.

## graphify

The graphify knowledge graph is generated locally and is **not** checked in
(`graphify-out/` is gitignored). Build it with `graphify update .` if you want it.

Rules, once it exists:
- Before answering architecture or codebase questions, read graphify-out/GRAPH_REPORT.md for god nodes and community structure
- If graphify-out/wiki/index.md exists, navigate it instead of reading raw files
- For cross-module "how does X relate to Y" questions, prefer `graphify query "<question>"`, `graphify path "<A>" "<B>"`, or `graphify explain "<concept>"` over grep — these traverse the graph's EXTRACTED + INFERRED edges instead of scanning files
- After modifying code files in this session, run `graphify update .` to keep the graph current (AST-only, no API cost)
