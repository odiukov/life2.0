# Shared Vector Memory + Real Embeddings — Design

**Date:** 2026-04-14
**Status:** Approved, pending implementation plan
**Author:** brainstorming session with Oleksandr

## Context

Current state (`shared/shared/vector.py`):

- Three per-agent Qdrant collections: `sleep_memories`, `workout_memories`, `nutrition_memories`.
- Fake 384-dim vectors derived from `hashlib.sha256(text)` — semantic search effectively returns random records.
- `upsert_memory(collection, id_, text, metadata)` / `search_memories(collection, query, limit)` — collection name is the cross-agent boundary.

Goal (part of the standards-compliance refactor series, item #2):

- One shared `health_memories` collection.
- Real multilingual embeddings so semantic search actually works.
- Cross-agent retrieval by default (sleep queries can surface nutrition context and vice versa).

## Decisions

| # | Decision | Rationale |
|---|----------|-----------|
| 1 | Embedding provider: **Google Gemini `text-embedding-004`** via REST | Free tier (~1500 req/day), 768 dims, solid multilingual (RU+EN). No extra SDK — raw httpx POST. |
| 2 | Vector size: **768**, collection: **`health_memories`** | Single collection, filter by `agent_id` payload field. |
| 3 | Default search scope: **all agents** | The point of shared memory — sleep should see nutrition context organically. Caller narrows with `agent_ids=[...]`. |
| 4 | Migration: **wipe** old collections | Fake vectors are worthless; dim change forces recreation anyway; history re-enters via `log_*` calls and (later) sync-service. |
| 5 | Sync-service → vector memory: **deferred to Plan 5** | Sync-service does not exist yet. Payload already carries `source: "agent"`; `"garmin"`/`"yazio"` slot in later without schema change. |
| 6 | Embedding error handling: **best-effort, non-fatal** | Postgres `health_logs` is source of truth; memory is aid, not dependency. |

## Architecture

### `shared/shared/embeddings.py` (new)

Single async function wrapping Gemini's `embedContent` endpoint.

```python
async def embed(text: str, task_type: str = "retrieval_document") -> list[float]:
    """POST https://generativelanguage.googleapis.com/v1beta/models/text-embedding-004:embedContent
    Returns 768-dim vector. Raises EmbeddingError on API failure."""
```

- Reads `GEMINI_API_KEY` at call time (fail-fast if unset).
- `task_type` switches between `"retrieval_document"` (stored text) and `"retrieval_query"` (search input) — Gemini treats them asymmetrically for better recall.
- Shared httpx.AsyncClient created lazily (module-level, same pattern as `_client` in vector.py).

### `shared/shared/vector.py` (rewrite)

Public API changes:

```python
VECTOR_SIZE = 768
COLLECTION = "health_memories"

async def ensure_collection() -> None: ...

async def upsert_memory(
    agent_id: str,           # "sleep" | "workout" | "nutrition"
    id_: str,
    text: str,
    metadata: dict,
) -> None:
    """Embed text, upsert with payload {agent_id, text, source: 'agent', **metadata}.
    Embedding errors are logged and swallowed — upsert is best-effort."""

async def search_memories(
    query: str,
    limit: int = 5,
    agent_ids: list[str] | None = None,   # None = all agents
) -> list[dict]:
    """Embed query, filter by agent_id if provided, return payload dicts.
    Embedding or Qdrant errors are logged and swallowed — returns []."""
```

- `ensure_collection()` creates `health_memories` with 768-dim cosine + payload index on `agent_id` (keyword index → fast `FieldCondition` filter).
- Collection parameter removed from public API. Internal constant only.

### Call-site updates

| File | Before | After |
|------|--------|-------|
| `agents/sleep/app/executor.py` | `upsert_memory("sleep_memories", id_, text, meta)` | `upsert_memory(agent_id="sleep", id_=id_, text=text, metadata=meta)` |
| `agents/workout/app/executor.py` | `upsert_memory("workout_memories", ...)` | `agent_id="workout"` |
| `agents/nutrition/app/executor.py` | `upsert_memory("nutrition_memories", ...)` | `agent_id="nutrition"` |
| `agents/sleep/app/prompt.py` | `search_memories("sleep_memories", task, 5)` | `search_memories(task, limit=5)` — cross-agent by default |
| `agents/workout/app/prompt.py` | `search_memories("workout_memories", task, 5)` | `search_memories(task, limit=5)` |
| `agents/nutrition/app/prompt.py` | `search_memories("nutrition_memories", task, 5)` | `search_memories(task, limit=5)` |

### Config

- `.env.example`: add `GEMINI_API_KEY=` line with link to `https://aistudio.google.com/apikey`.
- `.env`: user adds real key locally.
- `docker-compose.yml`: `GEMINI_API_KEY=${GEMINI_API_KEY}` propagated into `agent-sleep`, `agent-workout`, `agent-nutrition` service environments.
- No new Python dependencies (`httpx` already in `shared/requirements.txt`).

### Migration

One-shot shell script `scripts/wipe-vector-memory.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail
QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"
for c in sleep_memories workout_memories nutrition_memories; do
  curl -sS -X DELETE "$QDRANT_URL/collections/$c" | jq .
done
echo "Old collections dropped. New 'health_memories' will be created on first write."
```

Run once during deploy. `ensure_collection()` creates the new collection lazily on first upsert/search call.

## Error handling

| Scenario | Behaviour |
|----------|-----------|
| `GEMINI_API_KEY` unset | `embed()` raises `EmbeddingError` on first call — caught by `upsert_memory`/`search_memories` wrappers, logged as WARNING, op no-ops. Agent continues to work without memory. |
| Gemini 4xx/5xx / network error | Same as above — log + swallow. |
| Qdrant down | `search_memories` returns `[]` with log; `upsert_memory` logs + returns. Task completion is not blocked. |
| Empty text | `embed("")` skipped upstream in `upsert_memory` (no-op with log). |

## Testing

### Unit tests (new)

- `tests/test_embeddings.py`
  - Mocks `httpx.AsyncClient.post` — asserts correct URL, headers, body shape, task_type propagation.
  - Covers success, HTTP error, missing key.
- `tests/test_vector.py`
  - Mocks `embed()` and `AsyncQdrantClient`.
  - Verifies `upsert_memory` payload includes `agent_id`, `text`, `source: "agent"`, plus caller metadata.
  - Verifies `search_memories(agent_ids=["sleep","nutrition"])` builds a Qdrant `Filter` with `FieldCondition(key="agent_id", match=MatchAny(any=[...]))`.
  - Verifies `search_memories()` with no `agent_ids` passes no filter.
  - Verifies swallow-on-error paths (embed failure → `[]` / no-op).

### Unit tests (updated)

- `tests/test_sleep_executor.py`, `tests/test_workout_executor.py`, `tests/test_nutrition_executor.py` — update `upsert_memory` mock expectations to match new kwargs (`agent_id=…` instead of positional collection name).
- `tests/test_sleep_prompt.py`, `tests/test_workout_prompt.py`, `tests/test_nutrition_prompt.py` — update `search_memories` mock expectations (query-only signature).

### Manual smoke

1. `scripts/export-auth.sh && docker compose up -d`
2. `scripts/wipe-vector-memory.sh`
3. Via Telegram: log sleep "плохо спал из-за кофе" and nutrition "кофе в 22:00".
4. Sleep query "почему я плохо спал" — response should reference the 22:00 coffee (cross-agent retrieval).
5. `curl http://localhost:6333/collections/health_memories` → confirms 768-dim + 2 points + `agent_id` payload index.

## Out of scope

- Sync-service writing to vector memory (Plan 5).
- Embedding batch endpoints (no use case — single text per upsert/search).
- Embedding cache layer (YAGNI).
- Swapping the LLM provider for Claude CLI writes (unrelated to vector memory).
- Re-embedding historical fake-vector data (intentionally dropped).

## Follow-ups after this spec ships

- When Plan 5 (sync-service) starts: add `source: "garmin"` / `"yazio"` writes; no schema change needed.
- If free tier ever runs out: switch provider by editing one URL/model in `embeddings.py`. Payload and dim may change — would force re-wipe; acceptable since memory is rebuildable.
