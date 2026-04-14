# Shared Vector Memory + Real Embeddings Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace hash-based fake vectors and per-agent Qdrant collections with one shared `health_memories` collection backed by Google Gemini `text-embedding-004` embeddings, so semantic search actually works and sleep/workout/nutrition contexts cross-pollinate.

**Architecture:** New `shared/shared/embeddings.py` wraps Gemini's `embedContent` REST endpoint via httpx. `shared/shared/vector.py` is rewritten with a new API: `upsert_memory(agent_id, id_, text, metadata)` / `search_memories(query, limit, agent_ids=None)` that operates on a single 768-dim `health_memories` collection with a payload index on `agent_id`. All three agent executors and prompt builders switch to the new API. Old collections are wiped once during deploy.

**Tech Stack:** Python 3.12, httpx, qdrant-client 1.17+, pytest-asyncio, FastAPI/A2A-SDK 0.3.26.

**Spec:** `docs/superpowers/specs/2026-04-14-shared-vector-memory-design.md`

---

## File structure

**Create:**
- `shared/shared/embeddings.py` — Gemini `text-embedding-004` HTTP client
- `tests/test_embeddings.py` — unit tests for the client
- `tests/test_vector.py` — unit tests for `upsert_memory` / `search_memories`
- `scripts/wipe-vector-memory.sh` — one-shot legacy-collection cleanup

**Modify:**
- `shared/shared/vector.py` — full rewrite (new API, 768 dims, single collection)
- `agents/sleep/app/executor.py:134-144` — `upsert_memory` call
- `agents/sleep/app/prompt.py:7` — `search_memories` call
- `agents/workout/app/executor.py:134-144` — same
- `agents/workout/app/prompt.py:8` — same
- `agents/nutrition/app/executor.py:154-164` — same
- `agents/nutrition/app/prompt.py:31` — same
- `.env.example` — add `GEMINI_API_KEY=`
- `docker-compose.yml` — propagate `GEMINI_API_KEY` to the three `agent-*` services

No file currently imports `ensure_collection` directly, so that function becomes module-internal.

---

## Task 1: `embeddings.py` — Gemini HTTP client (TDD)

**Files:**
- Create: `shared/shared/embeddings.py`
- Create: `tests/test_embeddings.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_embeddings.py`:

```python
import os
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_embed_returns_vector_from_gemini_response():
    fake_response = AsyncMock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {"embedding": {"values": [0.1] * 768}}
    post = AsyncMock(return_value=fake_response)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
         patch("shared.embeddings._get_client") as gc:
        gc.return_value.post = post
        from shared.embeddings import embed
        vec = await embed("hello", task_type="retrieval_document")

    assert len(vec) == 768
    assert vec[0] == 0.1
    # URL contains the model
    call_url = post.await_args.args[0]
    assert "text-embedding-004:embedContent" in call_url
    # Body includes taskType and content
    body = post.await_args.kwargs["json"]
    assert body["content"]["parts"][0]["text"] == "hello"
    assert body["taskType"] == "RETRIEVAL_DOCUMENT"


@pytest.mark.asyncio
async def test_embed_maps_query_task_type():
    fake_response = AsyncMock()
    fake_response.raise_for_status = lambda: None
    fake_response.json = lambda: {"embedding": {"values": [0.0] * 768}}
    post = AsyncMock(return_value=fake_response)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
         patch("shared.embeddings._get_client") as gc:
        gc.return_value.post = post
        from shared.embeddings import embed
        await embed("q", task_type="retrieval_query")

    assert post.await_args.kwargs["json"]["taskType"] == "RETRIEVAL_QUERY"


@pytest.mark.asyncio
async def test_embed_raises_embedding_error_without_api_key():
    with patch.dict(os.environ, {}, clear=True):
        from shared.embeddings import embed, EmbeddingError
        with pytest.raises(EmbeddingError):
            await embed("hello")


@pytest.mark.asyncio
async def test_embed_wraps_http_error_in_embedding_error():
    import httpx
    fake_response = AsyncMock()
    fake_response.raise_for_status = AsyncMock(
        side_effect=httpx.HTTPStatusError(
            "500", request=AsyncMock(), response=AsyncMock(status_code=500)
        )
    )
    post = AsyncMock(return_value=fake_response)

    with patch.dict(os.environ, {"GEMINI_API_KEY": "k"}), \
         patch("shared.embeddings._get_client") as gc:
        gc.return_value.post = post
        from shared.embeddings import embed, EmbeddingError
        with pytest.raises(EmbeddingError):
            await embed("hello")
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_embeddings.py -v`
Expected: FAIL — `ModuleNotFoundError: No module named 'shared.embeddings'`.

- [ ] **Step 3: Implement `shared/shared/embeddings.py`**

```python
"""Google Gemini text-embedding-004 async HTTP client.

Wraps the generativelanguage.googleapis.com embedContent endpoint.
Returns 768-dim vectors. Raises EmbeddingError on any failure.
"""
from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

_MODEL = "text-embedding-004"
_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:embedContent"
_VECTOR_SIZE = 768

_client: httpx.AsyncClient | None = None


class EmbeddingError(RuntimeError):
    """Raised when Gemini embedding fails or is mis-configured."""


def _get_client() -> httpx.AsyncClient:
    global _client
    if _client is None:
        _client = httpx.AsyncClient(timeout=10.0)
    return _client


def _task_type(value: str) -> str:
    # Gemini expects uppercase enum values.
    mapping = {
        "retrieval_document": "RETRIEVAL_DOCUMENT",
        "retrieval_query": "RETRIEVAL_QUERY",
        "semantic_similarity": "SEMANTIC_SIMILARITY",
    }
    return mapping.get(value, "RETRIEVAL_DOCUMENT")


async def embed(text: str, task_type: str = "retrieval_document") -> list[float]:
    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        raise EmbeddingError("GEMINI_API_KEY is not set")

    client = _get_client()
    url = f"{_URL}?key={api_key}"
    body = {
        "model": f"models/{_MODEL}",
        "content": {"parts": [{"text": text}]},
        "taskType": _task_type(task_type),
    }
    try:
        response = await client.post(url, json=body)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        raise EmbeddingError(f"Gemini request failed: {e}") from e

    values = (data.get("embedding") or {}).get("values")
    if not values or len(values) != _VECTOR_SIZE:
        raise EmbeddingError(f"Unexpected embedding payload: {data}")
    return [float(v) for v in values]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_embeddings.py -v`
Expected: 4 passed.

- [ ] **Step 5: Commit**

```bash
git add shared/shared/embeddings.py tests/test_embeddings.py
git commit -m "feat(shared): add Gemini text-embedding-004 async client"
```

---

## Task 2: Rewrite `vector.py` for shared collection (TDD)

**Files:**
- Modify: `shared/shared/vector.py`
- Create: `tests/test_vector.py`

- [ ] **Step 1: Write the failing tests**

Write `tests/test_vector.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_upsert_memory_calls_embed_and_qdrant_with_payload():
    client = MagicMock()
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[
        MagicMock(name="health_memories"),
    ]))
    # force ensure_collection to create — pretend collection missing
    missing_collections = MagicMock()
    missing_collections.collections = []
    client.get_collections = AsyncMock(return_value=missing_collections)
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(return_value=[0.0] * 768)):
        from shared.vector import upsert_memory
        await upsert_memory(
            agent_id="sleep", id_="abc", text="плохо спал",
            metadata={"skill": "log_sleep"},
        )

    client.create_collection.assert_awaited_once()
    client.create_payload_index.assert_awaited_once()
    assert client.upsert.await_count == 1
    kwargs = client.upsert.await_args.kwargs
    assert kwargs["collection_name"] == "health_memories"
    point = kwargs["points"][0]
    assert point.payload["agent_id"] == "sleep"
    assert point.payload["text"] == "плохо спал"
    assert point.payload["source"] == "agent"
    assert point.payload["skill"] == "log_sleep"
    assert len(point.vector) == 768


@pytest.mark.asyncio
async def test_search_memories_without_agent_ids_passes_no_filter():
    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)
    client.query_points = AsyncMock(return_value=MagicMock(points=[
        MagicMock(payload={"text": "m1", "agent_id": "sleep"}),
    ]))

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(return_value=[0.0] * 768)):
        from shared.vector import search_memories
        out = await search_memories("query", limit=3)

    assert out == [{"text": "m1", "agent_id": "sleep"}]
    kwargs = client.query_points.await_args.kwargs
    assert kwargs["collection_name"] == "health_memories"
    assert kwargs["limit"] == 3
    assert kwargs.get("query_filter") is None


@pytest.mark.asyncio
async def test_search_memories_with_agent_ids_builds_match_any_filter():
    from qdrant_client.models import Filter, FieldCondition, MatchAny
    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)
    client.query_points = AsyncMock(return_value=MagicMock(points=[]))

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(return_value=[0.0] * 768)):
        from shared.vector import search_memories
        await search_memories("q", limit=5, agent_ids=["sleep", "nutrition"])

    qf = client.query_points.await_args.kwargs["query_filter"]
    assert isinstance(qf, Filter)
    cond = qf.must[0]
    assert isinstance(cond, FieldCondition)
    assert cond.key == "agent_id"
    assert isinstance(cond.match, MatchAny)
    assert set(cond.match.any) == {"sleep", "nutrition"}


@pytest.mark.asyncio
async def test_upsert_memory_swallows_embedding_error():
    from shared.embeddings import EmbeddingError
    client = MagicMock()
    client.get_collections = AsyncMock(return_value=MagicMock(collections=[]))
    client.create_collection = AsyncMock()
    client.create_payload_index = AsyncMock()
    client.upsert = AsyncMock()

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(side_effect=EmbeddingError("boom"))):
        from shared.vector import upsert_memory
        await upsert_memory(agent_id="sleep", id_="abc", text="t", metadata={})

    client.upsert.assert_not_awaited()


@pytest.mark.asyncio
async def test_search_memories_swallows_embedding_error_returns_empty():
    from shared.embeddings import EmbeddingError
    client = MagicMock()
    present = MagicMock()
    present.collections = [MagicMock()]
    present.collections[0].name = "health_memories"
    client.get_collections = AsyncMock(return_value=present)

    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock(side_effect=EmbeddingError("boom"))):
        from shared.vector import search_memories
        out = await search_memories("q")

    assert out == []


@pytest.mark.asyncio
async def test_upsert_memory_skips_empty_text():
    client = MagicMock()
    client.upsert = AsyncMock()
    with patch("shared.vector._get_client", return_value=client), \
         patch("shared.vector.embed", new=AsyncMock()) as emb:
        from shared.vector import upsert_memory
        await upsert_memory(agent_id="sleep", id_="x", text="   ", metadata={})
    emb.assert_not_called()
    client.upsert.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest tests/test_vector.py -v`
Expected: FAIL — current `upsert_memory` signature takes `collection` positional, tests use new kwargs.

- [ ] **Step 3: Rewrite `shared/shared/vector.py`**

Replace the entire file with:

```python
"""Shared Qdrant vector memory for health agents.

One collection `health_memories` holds memories from all agents. Each point's
payload carries `agent_id` (sleep/workout/nutrition), `text`, `source`
(agent/garmin/yazio/…), plus caller-supplied metadata. Cross-agent search is
the default; narrow scope with `agent_ids=[...]`.

Embeddings come from Gemini `text-embedding-004` (768 dims). Embedding or
Qdrant failures are logged and swallowed — memory is best-effort; the Postgres
`health_logs` table is source of truth.
"""
from __future__ import annotations

import hashlib
import logging
import os

from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from shared.embeddings import EmbeddingError, embed

logger = logging.getLogger(__name__)

VECTOR_SIZE = 768
COLLECTION = "health_memories"

_client: AsyncQdrantClient | None = None


def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            host=os.environ.get("QDRANT_HOST", "localhost"),
            port=int(os.environ.get("QDRANT_PORT", 6333)),
        )
    return _client


async def _ensure_collection() -> None:
    client = _get_client()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if COLLECTION in names:
        return
    await client.create_collection(
        collection_name=COLLECTION,
        vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
    )
    await client.create_payload_index(
        collection_name=COLLECTION,
        field_name="agent_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )


def _point_id(id_: str) -> int:
    return int(hashlib.sha256(id_.encode()).hexdigest()[:16], 16) % (2**63)


async def upsert_memory(
    agent_id: str,
    id_: str,
    text: str,
    metadata: dict,
) -> None:
    if not text or not text.strip():
        return
    try:
        vector = await embed(text, task_type="retrieval_document")
    except EmbeddingError as e:
        logger.warning("embed failed for upsert (agent=%s, id=%s): %s", agent_id, id_, e)
        return
    try:
        client = _get_client()
        await _ensure_collection()
        payload = {
            "agent_id": agent_id,
            "text": text,
            "source": metadata.pop("source", "agent"),
            **metadata,
        }
        await client.upsert(
            collection_name=COLLECTION,
            points=[PointStruct(id=_point_id(id_), vector=vector, payload=payload)],
        )
    except Exception as e:
        logger.warning("qdrant upsert failed (agent=%s, id=%s): %s", agent_id, id_, e)


async def search_memories(
    query: str,
    limit: int = 5,
    agent_ids: list[str] | None = None,
) -> list[dict]:
    try:
        vector = await embed(query, task_type="retrieval_query")
    except EmbeddingError as e:
        logger.warning("embed failed for search: %s", e)
        return []
    try:
        client = _get_client()
        await _ensure_collection()
        qf = None
        if agent_ids:
            qf = Filter(must=[FieldCondition(key="agent_id", match=MatchAny(any=agent_ids))])
        results = await client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=qf,
        )
        return [r.payload for r in results.points]
    except Exception as e:
        logger.warning("qdrant search failed: %s", e)
        return []
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest tests/test_vector.py tests/test_embeddings.py -v`
Expected: all green.

- [ ] **Step 5: Commit**

```bash
git add shared/shared/vector.py tests/test_vector.py
git commit -m "refactor(shared): single health_memories collection with real embeddings"
```

---

## Task 3: Update sleep agent call sites

**Files:**
- Modify: `agents/sleep/app/executor.py:134-144`
- Modify: `agents/sleep/app/prompt.py:7`
- Modify: `tests/test_sleep_executor.py` (only if argument-shape assertions need updating — current tests just mock `upsert_memory` without asserting args, so probably no change)

- [ ] **Step 1: Update `executor.py`**

Replace the `upsert_memory(...)` block at `agents/sleep/app/executor.py:134-144`:

```python
                await upsert_memory(
                    agent_id="sleep",
                    id_=str(uuid.uuid4()),
                    text=output,
                    metadata={
                        "skill": skill_id,
                        "params": json.dumps(
                            {k: v for k, v in params.items() if k != "peer_artifacts"}
                        ),
                    },
                )
```

- [ ] **Step 2: Update `prompt.py`**

Replace `agents/sleep/app/prompt.py:7`:

```python
    memories = await search_memories(task, limit=5)
```

(Drop the collection name argument; cross-agent scope is now the default.)

- [ ] **Step 3: Run sleep tests**

Run: `pytest tests/test_sleep_executor.py tests/test_sleep_prompt.py -v`
Expected: all green — existing mocks are call-shape-agnostic; prompt test merely expects `search_memories` to be awaited once.

If a prompt test asserts a specific collection string, drop that assertion. Check:
```bash
grep -n "sleep_memories" tests/test_sleep_prompt.py
```
If found, remove those assertions.

- [ ] **Step 4: Commit**

```bash
git add agents/sleep/app/executor.py agents/sleep/app/prompt.py tests/test_sleep_prompt.py 2>/dev/null
git commit -m "refactor(sleep): use shared health_memories via new vector API"
```

(The `2>/dev/null` handles the case where the test file didn't change.)

---

## Task 4: Update workout agent call sites

**Files:**
- Modify: `agents/workout/app/executor.py:134-144`
- Modify: `agents/workout/app/prompt.py:8`

- [ ] **Step 1: Update `executor.py`**

Replace the `upsert_memory(...)` block at `agents/workout/app/executor.py:134-144`:

```python
                await upsert_memory(
                    agent_id="workout",
                    id_=str(uuid.uuid4()),
                    text=output,
                    metadata={
                        "skill": skill_id,
                        "params": json.dumps(
                            {k: v for k, v in params.items() if k != "peer_artifacts"}
                        ),
                    },
                )
```

- [ ] **Step 2: Update `prompt.py`**

Replace `agents/workout/app/prompt.py:8`:

```python
    memories = await search_memories(task, limit=5)
```

- [ ] **Step 3: Run workout tests**

Run: `pytest tests/test_workout_executor.py tests/test_workout_prompt.py -v`
Expected: all green. If any assertion mentions `workout_memories`, drop it.

- [ ] **Step 4: Commit**

```bash
git add agents/workout/app/executor.py agents/workout/app/prompt.py tests/test_workout_prompt.py 2>/dev/null
git commit -m "refactor(workout): use shared health_memories via new vector API"
```

---

## Task 5: Update nutrition agent call sites

**Files:**
- Modify: `agents/nutrition/app/executor.py:154-164`
- Modify: `agents/nutrition/app/prompt.py:31`

- [ ] **Step 1: Update `executor.py`**

Replace the `upsert_memory(...)` block at `agents/nutrition/app/executor.py:154-164`:

```python
                await upsert_memory(
                    agent_id="nutrition",
                    id_=str(uuid.uuid4()),
                    text=output,
                    metadata={
                        "skill": skill_id,
                        "params": json.dumps(
                            {k: v for k, v in params.items() if k != "peer_artifacts"}
                        ),
                    },
                )
```

- [ ] **Step 2: Update `prompt.py`**

Replace `agents/nutrition/app/prompt.py:31`:

```python
    memories = await search_memories(task, limit=5)
```

- [ ] **Step 3: Run nutrition tests**

Run: `pytest tests/test_nutrition_executor.py tests/test_nutrition_prompt.py -v`
Expected: all green. If any assertion mentions `nutrition_memories`, drop it.

- [ ] **Step 4: Commit**

```bash
git add agents/nutrition/app/executor.py agents/nutrition/app/prompt.py tests/test_nutrition_prompt.py 2>/dev/null
git commit -m "refactor(nutrition): use shared health_memories via new vector API"
```

---

## Task 6: Config + wipe script

**Files:**
- Modify: `.env.example` (and manually `.env`, not committed)
- Modify: `docker-compose.yml` (3 agent services)
- Create: `scripts/wipe-vector-memory.sh`

- [ ] **Step 1: Add `GEMINI_API_KEY` to `.env.example`**

Append to the bottom of `.env.example`:

```
# Google Gemini text-embedding-004 — free tier at https://aistudio.google.com/apikey
GEMINI_API_KEY=
```

And add the same line with a real key to local `.env` (not committed — user does this manually).

- [ ] **Step 2: Propagate `GEMINI_API_KEY` to agents in `docker-compose.yml`**

In each of `agent-sleep`, `agent-workout`, `agent-nutrition`, under `environment:`, add:

```yaml
      GEMINI_API_KEY: ${GEMINI_API_KEY}
```

Target lines:
- `agent-sleep` — under the existing `QDRANT_PORT: ${QDRANT_PORT}` (around line 41)
- `agent-workout` — around line 69
- `agent-nutrition` — around line 97 (before `SYNC_SERVICE_URL`)

- [ ] **Step 3: Create `scripts/wipe-vector-memory.sh`**

```bash
#!/usr/bin/env bash
# One-shot: drop legacy per-agent Qdrant collections after migrating to
# the shared health_memories collection. Safe to run multiple times;
# missing collections are reported as 404 and ignored.
set -euo pipefail

QDRANT_URL="${QDRANT_URL:-http://localhost:6333}"

for c in sleep_memories workout_memories nutrition_memories; do
  echo "Dropping $c ..."
  curl -sS -X DELETE "$QDRANT_URL/collections/$c" || true
  echo
done
echo "Done. 'health_memories' will be created lazily on first upsert/search."
```

Then make it executable:

```bash
chmod +x scripts/wipe-vector-memory.sh
```

- [ ] **Step 4: Commit**

```bash
git add .env.example docker-compose.yml scripts/wipe-vector-memory.sh
git commit -m "chore(ops): wire GEMINI_API_KEY and legacy-collection wipe script"
```

---

## Task 7: Full regression + manual smoke

**Files:** none.

- [ ] **Step 1: Run the full suite**

Run: `pytest -v`
Expected: all tests pass. If any lingering test references the old `sleep_memories` / `workout_memories` / `nutrition_memories` strings, fix inline and include in a follow-up commit.

- [ ] **Step 2: Write `GEMINI_API_KEY` into local `.env`**

Manual: add `GEMINI_API_KEY=<real key>` to `/Users/oleksandr/Documents/life-agents/.env`. Use any key from https://aistudio.google.com/apikey.

- [ ] **Step 3: Bring stack up and wipe legacy collections**

```bash
scripts/export-auth.sh
docker compose up -d --build agent-sleep agent-workout agent-nutrition
scripts/wipe-vector-memory.sh
```

- [ ] **Step 4: Smoke cross-agent memory retrieval via Telegram**

1. `/nutrition кофе в 22:00` — nutrition agent logs the meal; a memory is stored with `agent_id="nutrition"`.
2. `/sleep почему я плохо спал вчера` — sleep agent's `search_memories(task)` should surface the nutrition memory. Confirm the LLM response references the late coffee.
3. `curl http://localhost:6333/collections/health_memories | jq` — expect 768-dim config, ≥2 points, `agent_id` in payload schema.

- [ ] **Step 5: Commit anything that shifted during smoke**

If tests needed tweaks:

```bash
git add -A
git commit -m "test: align with shared-memory API"
```

Otherwise no commit needed.

---

## Self-review checklist (for the implementer)

- Is `GEMINI_API_KEY` set in local `.env` before running the stack? A missing key makes memory ops no-op (not fatal), but smoke test #4 will return empty.
- Did you run `scripts/wipe-vector-memory.sh` after first deploy? Old 384-dim collections would otherwise linger (harmless but confusing).
- Does `curl .../collections/health_memories` show `agent_id` as an indexed payload field? If not, check `_ensure_collection()` ran (first upsert/search triggers it).
- Are there any surviving references to `sleep_memories` / `workout_memories` / `nutrition_memories` in agent code or tests? `grep -rn "_memories\"" agents tests` should return nothing.
