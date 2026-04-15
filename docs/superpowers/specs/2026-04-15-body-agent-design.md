# Body Agent — Design Spec

**Date:** 2026-04-15
**Status:** Approved (brainstorming), pending implementation plan
**Scope:** Add a new A2A peer agent `body` that owns body-composition data (weight, body fat %, muscle mass, etc.) already ingested via Telegram PDF upload from ViHealth/LePulse scales.

## Motivation

`health_logs` already stores `type='body_composition'` rows with rich metrics, populated by the Telegram → `vihealth.py` (Claude Vision) → `/sync/body` pipeline. But the orchestrator's LangGraph ReAct agent has no tool that reads this data: it only knows `ask_sleep_agent`, `ask_workout_agent`, `ask_nutrition_agent`, plus `sync_health_data` and `send_daily_briefing`. Queries like "сколько я вешу" or "проанализируй историю веса" fail — the LLM has no route to the data.

Chosen solution: a new A2A peer agent following the established sleep/workout/nutrition pattern. This keeps the LLM path clean (reasoning always goes through A2A, never direct DB) while leaving dashboard/stats endpoints as-is.

## Non-goals

- No change to the PDF parser (Claude Vision extraction stays as-is).
- No `log_*` skill. Body data arrives via sync, not manual entry.
- No FHIR/LOINC mapping. Consumer-grade naming (Apple HealthKit) is sufficient.
- No refactor of orchestrator's direct Postgres access for dashboard endpoints.

## Architecture

New service `agent-body` at port **8004**, structurally symmetric to `agents/sleep`:

- FastAPI app wrapping `A2AStarletteApplication` (a2a-sdk 0.3.26)
- AgentCard at `/.well-known/agent.json` with `protocolVersion:"0.3.0"`, `preferredTransport:"JSONRPC"`, two skills
- `PostgresTaskStore` for Task lifecycle
- Claude CLI via `shared/claude_runner.py` (OAuth token from `.env.auth`)
- Writes analysis summaries to shared `health_memories` Qdrant collection (`agent_id="body"`)

Orchestrator integration:
- New tool `ask_body_agent(message, skill)` in `orchestrator/app/health_agent.py`
- Registration in `orchestrator/app/registry.py`: `"body": "http://agent-body:8004"`

Telegram bot:
- New `/body` command in `telegram_bot/app/bot.py`, analogous to `/sleep` etc.

## Skills

### `get_latest_body`
Returns the most recent body composition measurement as a short textual summary plus key figures.

- **Prefetch:** `SELECT … FROM health_logs WHERE type='body_composition' ORDER BY recorded_at DESC LIMIT 1`
- **Prompt:** latest metrics + date, ask Claude for a one-sentence summary
- **Empty case:** prefetch returns no rows → prompt instructs Claude to tell the user there is no data yet and suggest uploading a ViHealth PDF

### `analyze_body_trend`
Analyzes body-composition dynamics over a period (default 30 days; LLM may override via message text) and correlates with nutrition and workouts.

- **Prefetch (parallel):**
  - body_composition rows over the period
  - nutrition rows (daily kcal, protein/fat/carbs) over the same period
  - workout rows (volume, type, duration) over the same period
- **Prompt:** three tables + instruction to discuss weight/fat/muscle trend, correlate with intake and training, give 1–2 concrete recommendations
- **Side effect:** writes the analysis summary to `health_memories` with `agent_id="body"`, metadata `{skill: "analyze_body_trend", period_days: N}`

## Reverse cross-context

Body data becomes visible to peer agents so their prompts can use it directly:

- `agents/nutrition/app/prompt.py` — in `analyze_nutrition` and `get_nutrition_recommendations`, prefetch the latest body row to derive BMR (for TDEE estimation) and weight (for protein/kg targets)
- `agents/workout/app/prompt.py` — in `analyze_workout` and `get_workout_recommendations`, include latest body row so recommendations can reference lean body mass

Implementation: one additional prefetch call + one additional section in the prompt. Same data access pattern already used for existing cross-agent context.

## Data

No schema changes to Postgres. `health_logs` already has `type='body_composition'` with JSONB `data`.

**Current state (pre-this-spec):** only 6 metrics reach the DB — `weight_kg`, `body_fat_pct`, `bmi`, `skeletal_muscle_kg`, `bone_mass_kg`, `lean_mass_kg`. Everything else the Vision parser extracts (`bmr_kcal`, `visceral_fat_grade`, `body_age`, `body_score`, `subcutaneous_fat_pct`, `protein_kg`, `body_water_kg`, `muscle_kg`, `body_fat_kg`, `fat_free_kg`) is dropped by `build_sync_payload` in `telegram_bot/app/vihealth.py` and `sync_service/app/vihealth_pdf.py`.

**In scope:** widen both payload builders to emit the richer set so `analyze_body_trend` has BMR/visceral-fat/etc. to reason about. Two options:

1. **Extend Apple Health metric mapping** — add entries for each new metric to `_METRIC_MAP` in `sync_service/app/apple_health.py` and to the `mapping` dicts in both `vihealth.py` and `vihealth_pdf.py`. Uses invented HealthKit-style names for fields with no HealthKit equivalent (e.g. body_score, body_age).
2. **Bypass apple_health mapping for ViHealth** — have both `build_sync_payload` functions emit the raw internal keys directly into a new `/sync/body/vihealth` endpoint that writes straight to `health_logs` without going through `map_body_composition`. Keeps HealthKit naming clean but adds a second code path.

**Recommendation: option 1.** Extending `_METRIC_MAP` is one dict change per file and keeps a single ingestion path. Backfill not required — historical rows keep the old narrow shape; the body agent tolerates missing fields.

New helper `shared/db.py::fetch_body_composition(start, end)` returning rows over a range, mirroring `fetch_sleep_logs` / `fetch_workout_logs` / `fetch_nutrition_logs`.

## Error handling

- **No data in period:** prefetch returns empty list → prompt tells Claude to respond with a soft "no measurements for this period" message. No exception.
- **Qdrant write failure:** swallowed (best-effort). Postgres is source of truth.
- **Claude CLI failure:** propagates as A2A Task in `failed` state. Orchestrator's existing `_call_agent_with_artifact` handles empty text via fallback message.
- **Agent unreachable** (`agent-body` container down): `_resolve_url("body")` returns `None` → existing fallback `"Agent 'body' is currently unavailable"` in `health_agent.py`.
- **Unparseable period in message:** prompt-builder falls back to 30 days.

## Testing

- **Unit:** `tests/test_body_prompt.py` — prompt assembly with mocked DB for cases: empty series, single measurement, multi-point series, cross-context (nutrition + workout present/absent).
- **Unit:** `tests/test_nutrition_prompt.py` and `tests/test_workout_prompt.py` — extend existing tests with a body-row fixture to verify reverse cross-context renders.
- **Smoke:** `scripts/smoke-body-agent.sh` — brings the stack up, sends A2A `message/send` with `skillId: get_latest_body`, asserts non-empty response. Mirrors `scripts/smoke-*` siblings.
- **Manual integration:** send "сколько я вешу" in Telegram → orchestrator LLM calls `ask_body_agent(skill='get_latest_body')` → response contains the weight from the latest PDF upload.

## Standards compliance

- **A2A v0.3 (Google):** canonical via `a2a-sdk 0.3.26`. AgentCard shape, JSONRPC methods, `PostgresTaskStore` — same as existing agents.
- **Apple HealthKit naming:** body metrics stored under HealthKit-style names via `map_body_composition`. Consumer-grade de facto standard.
- **Units:** kg / % / kcal (SI), consistent with the rest of the stack.
- **UTC timestamps:** timezone-aware `recorded_at`.

Known deviations (intentional):
- Skill asymmetry: no `log_*` (ingestion is external), no `get_body_recommendations` (subsumed by `analyze_body_trend`).
- Static service registry (`registry.py`) instead of DNS-SD / A2A registry service — acceptable for docker-compose single-host.
- No FHIR/LOINC — out of scope for consumer stack.
- No OpenTelemetry — project-wide gap, not body-specific.

## Deployment

- `docker-compose.yml`: new service `agent-body`, copy of `agent-nutrition` block with `AGENT_ID=body`, port 8004, Dockerfile path `agents/body/Dockerfile` (build context = repo root).
- Env: `DATABASE_URL`, `QDRANT_HOST`, `GEMINI_API_KEY`, `ANTHROPIC_API_KEY` (OAuth token from `scripts/export-auth.sh`), `LLM_PROVIDER`.
- Requirements: same base as other agents (a2a-sdk, fastapi, asyncpg, qdrant-client, httpx, sse-starlette).
- Registry: add `"body": "http://agent-body:8004"` in `orchestrator/app/registry.py`.

## Rollout

One PR introducing:
1. Widen ingestion mapping (`_METRIC_MAP` in `sync_service/app/apple_health.py`; `mapping` in `telegram_bot/app/vihealth.py` and `sync_service/app/vihealth_pdf.py`) so BMR, visceral fat, body age, body score, subcutaneous fat %, protein, body water, muscle, body fat kg, fat-free mass land in `health_logs.data`.
2. `agents/body/` service (skeleton, skills, prompt builder, Dockerfile)
3. `shared/db.py` helper `fetch_body_composition`
4. Orchestrator tool + registry entry
5. Reverse cross-context in nutrition/workout prompt builders
6. Telegram `/body` command
7. Tests + smoke script
8. `docker-compose.yml` service entry

Post-merge: verify via Telegram "сколько я вешу" and "проанализируй историю веса".
