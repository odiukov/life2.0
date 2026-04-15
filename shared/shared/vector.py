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
        md = dict(metadata)
        payload = {
            "agent_id": agent_id,
            "text": text,
            "source": md.pop("source", "agent"),
            **md,
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
