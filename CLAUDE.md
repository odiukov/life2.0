# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

### Python

```bash
make sync               # uv sync --all-packages --all-extras (creates .venv)
make lint               # ruff, formatting, strict mypy for new code, import-linter
make test               # unit tests (no Docker)
make test-integration   # PostgreSQL testcontainers (needs Docker)
make evals              # real-LLM golden sets (needs a genuine provider key)
uv run pytest agents/nutrition/tests/unit/test_log_meal.py -q
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
docker compose up --build -d          # Build + start services
docker compose ps                     # Check health
docker compose logs -f orchestrator   # Follow a service
# LLM env changes need --force-recreate, not just restart
docker compose up --force-recreate orchestrator
```

### Smoke tests (require running stack)

```bash
bash scripts/smoke-mood.sh
bash scripts/smoke-vector-memory.sh
# Full chat and agent checks: scripts/acceptance_orchestrator.sh
```

### Database migrations

```bash
# Alembic, applied by the migrate compose service on every docker compose up.
make migrate   # python -m shared.schema; needs POSTGRES_* and APP_*_PASSWORD
# Update shared/src/shared/schema/tables.py and add an Alembic revision under
# shared/src/shared/schema/alembic/versions/ together; test_schema.py checks parity.
```

## Architecture

### Service map

```
Frontend:   React Native (apps/mobile)
                │
Orchestrator (:8000) — LangGraph ReAct agent, manages tasks and transcripts in PostgreSQL,
                       serves /tasks and task SSE to the mobile app, calls peer agents via A2A SDK
                │
12 Peer Agents — sleep, workout, nutrition, body, mood, habits, recovery, medication, kitchen, finance, calendar, home
                               Each is a FastAPI + A2A SDK server with 3–4 domain skills
STT (:8010, internal) — local faster-whisper speech-to-text over HTTP
                │
Sync Service (:8080) — polls Garmin & Yazio on schedule, triggers briefing;
                │
Data: PostgreSQL (health_logs, tasks, LangGraph checkpoints) + Qdrant (vector memory)
Observability: self-hosted Langfuse v3 stack (:3100), OTEL via Traceloop SDK
```

### Key patterns

**Agent structure** — all health peers use the foundation layout with domain, application, adapters and composition modules:

The new `household` library and `agents/kitchen` follow the same layered layout: pure
`domain`, port-dependent `application`, infrastructure `adapters`, and `composition.py`
for wiring. `gateway` mounts typed household, kitchen, voice and notification routes in the
orchestrator. `stt_service` is an internal HTTP service with its own settings and adapter.
Agents speak only A2A; the app reaches them through the gateway, never directly.

```
agents/<name>/src/<name>/
  domain/       # pure types and rules
  application/  # use cases, AnalysisData and schemas on ports
  adapters/     # SQL repositories and A2A card/executor/spec
  composition.py # dependency wiring
  main.py       # service entry point
```

**Adding skills**: for analysis, implement `AnalysisData`, register a tail for the skill in
`AnalysisSpec`, and add a prompt snapshot test. The shared `AnalysisSkill` loads tenant data,
fetches selected peers and optional memories, composes the prompt, calls the model and saves
memory. Read raw health logs through `HealthLogRepository`, then map rows to domain types.
For writes, add an application use case and extraction schema, a stored-row shape test,
and real-provider eval cases. User-facing text must use locale keys through `Translator`;
keep English extraction instructions separate from localized replies.

**health_logs table** is the universal sink. Dedup key is `(user_id, source, type, recorded_at)` — not an upsert, so duplicates are blocked on insert. Every agent uses `agent='sleep'|'workout'|...` when reading; the aggregator agent column must always be set when writing (see healthkit_aggregator_agent_column memory).

**Household tenancy**: `app.user_id` remains the only tenant context passed by services.
PostgreSQL's `current_household_id()` derives membership; `app_rw` sees household rows
through RLS. `HOUSEHOLD_TABLES` in `shared.schema.tables` mirrors the SQL
`household_tables` registry, which drives join transfers and item counts. Household-scoped
tables use `ENABLE ROW LEVEL SECURITY` without `FORCE`, because the table-owner membership
functions must move rows between households. Every new household-scoped table must be added
to `HOUSEHOLD_TABLES` and to the registry in its migration.

**A2A flow**: orchestrator calls peer agents over HTTP using `google-a2a` SDK. Each peer skill receives an A2A Message, runs its LLM prompt, persists results, and streams artifacts back. Peer artifact fetching (for cross-domain context) lives in `shared/adapters/peers.py`.

**LangGraph checkpointing**: conversation state is stored per task ID in PostgreSQL via `AsyncPostgresSaver`. The mobile app restores task cards and transcripts through `/tasks`.

**Shared Python library**: `shared/src/shared/` is installed through the uv workspace (`make sync`) into every Python service. Add cross-service utilities here (LLM factory, DB helpers, A2A client cache, vector ops, telemetry init).

**LLM factory**: services use typed `LLM__DEFAULT` / `LLM__TASKS__*` routes and the shared LLM adapters.

**Telemetry**: call `init_telemetry("service-name")` before application imports in `serve.py`. Composition configures privacy-safe logging before constructing adapters. Three consent modes: `full` (dev), `metadata` (token counts only), `consented` (per-user opt-in via `telemetry_consent` table).

### Directory layout

```
agents/           12 layered peer agents
household/        Household domain, application and SQL adapter
gateway/          Typed gateway routes mounted in orchestrator
stt_service/      Internal speech-to-text HTTP service
orchestrator/     LangGraph orchestrator + all specialized modules
sync_service/     Garmin/Yazio poller
apps/
  mobile/         React Native (Expo 54) — HealthKit, share extension, offline SQLite
packages/
  api-client/     OpenAPI-generated TypeScript client (shared by web + mobile)
  i18n/           Russian + English strings
  ui/             Shared React components
shared/           Python shared library (SQLAlchemy, LLM adapters, A2A, Qdrant, telemetry)
shared/src/shared/schema/ SQLAlchemy metadata and Alembic migrations
scripts/          smoke and acceptance scripts
```

### Integration quirks

- **Yazio**: v18 API has 3 distinct entry shapes; `insert_rows` behaves as UPSERT; sleep query uses "most recent" window, not yesterday.
- **Google Calendar**: direct REST calls from `agents/calendar` with per-user OAuth tokens from the credential store — no MCP server in the path.
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
