"""Tenant-scoped Qdrant memory with Gemini embeddings and best-effort writes."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping, Sequence
from uuid import UUID

import httpx
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance,
    FieldCondition,
    Filter,
    MatchAny,
    MatchValue,
    PayloadSchemaType,
    PointStruct,
    VectorParams,
)

from shared.config.adapter_services import VectorSettings
from shared.observability.logging import get_logger
from shared.ports.vector_memory import Memory

logger = get_logger(__name__)

VECTOR_SIZE = 768
COLLECTION = "health_memories"

_client: AsyncQdrantClient | None = None


def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            host=VectorSettings().qdrant_host,
            port=VectorSettings().qdrant_port,
        )
    return _client


async def _ensure_collection() -> None:
    client = _get_client()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if COLLECTION not in names:
        await client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )
    # Idempotent: Qdrant raises if index exists; we swallow.
    for field in ("agent_id", "user_id"):
        try:
            await client.create_payload_index(
                collection_name=COLLECTION,
                field_name=field,
                field_schema=PayloadSchemaType.KEYWORD,
            )
        except Exception:
            pass


def _point_id(id_: str) -> int:
    return int(hashlib.sha256(id_.encode()).hexdigest()[:16], 16) % (2**63)


async def _upsert(
    user_id: UUID,
    agent_id: str,
    id_: str,
    text: str,
    metadata: dict[str, str],
) -> None:
    if not text or not text.strip():
        return
    try:
        vector = await _embed(text, task_type="retrieval_document")
    except EmbeddingError as e:
        logger.warning("vector_embedding_failed", agent=agent_id, error_type=type(e).__name__)
        return
    try:
        client = _get_client()
        await _ensure_collection()
        md = dict(metadata)
        payload = {
            "user_id": str(user_id),
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
        logger.warning("vector_upsert_failed", agent=agent_id, error_type=type(e).__name__)


async def _search(
    user_id: UUID,
    query: str,
    limit: int = 5,
    agent_ids: list[str] | None = None,
) -> list[dict[str, object]]:
    try:
        vector = await _embed(query, task_type="retrieval_query")
    except EmbeddingError as e:
        logger.warning("vector_embedding_failed", error_type=type(e).__name__)
        return []
    try:
        client = _get_client()
        await _ensure_collection()
        must = [FieldCondition(key="user_id", match=MatchValue(value=str(user_id)))]
        if agent_ids:
            must.append(FieldCondition(key="agent_id", match=MatchAny(any=agent_ids)))
        qf = Filter(must=must)
        results = await client.query_points(
            collection_name=COLLECTION,
            query=vector,
            limit=limit,
            with_payload=True,
            query_filter=qf,
        )
        return [r.payload for r in results.points if r.payload is not None]
    except Exception as e:
        logger.warning("vector_search_failed", error_type=type(e).__name__)
        return []


_MODEL = "gemini-embedding-001"
_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{_MODEL}:embedContent"
_VECTOR_SIZE = 768

_embedding_client: httpx.AsyncClient | None = None


class EmbeddingError(RuntimeError):
    """Raised when Gemini embedding fails or is mis-configured."""


def _get_embedding_client() -> httpx.AsyncClient:
    global _embedding_client
    if _embedding_client is None:
        _embedding_client = httpx.AsyncClient(timeout=10.0)
    return _embedding_client


def _task_type(value: str) -> str:
    # Gemini expects uppercase enum values.
    mapping = {
        "retrieval_document": "RETRIEVAL_DOCUMENT",
        "retrieval_query": "RETRIEVAL_QUERY",
        "semantic_similarity": "SEMANTIC_SIMILARITY",
    }
    return mapping.get(value, "RETRIEVAL_DOCUMENT")


async def _embed(text: str, task_type: str = "retrieval_document") -> list[float]:
    secret = VectorSettings().gemini_api_key
    api_key = secret.get_secret_value() if secret else None
    if not api_key:
        raise EmbeddingError("GEMINI_API_KEY is not set")

    client = _get_embedding_client()
    url = f"{_URL}?key={api_key}"
    body = {
        "model": f"models/{_MODEL}",
        "content": {"parts": [{"text": text}]},
        "taskType": _task_type(task_type),
        "outputDimensionality": _VECTOR_SIZE,
    }
    try:
        response = await client.post(url, json=body)
        response.raise_for_status()
        data = response.json()
    except httpx.HTTPError as e:
        raise EmbeddingError("embedding_request_failed") from e

    values = (data.get("embedding") or {}).get("values")
    if not values or len(values) != _VECTOR_SIZE:
        raise EmbeddingError("embedding_payload_invalid")
    return [float(v) for v in values]


_RESERVED = {"text", "agent_id", "user_id"}


class QdrantVectorMemory:
    async def upsert(
        self, *, user_id: UUID, agent: str, key: str, text: str, metadata: Mapping[str, str]
    ) -> None:
        # Legacy point ids are global: encode the complete logical identity.
        identity = json.dumps([str(user_id), agent, key], separators=(",", ":"))
        try:
            await _upsert(
                user_id=user_id,
                agent_id=agent,
                id_=identity,
                text=text,
                metadata={name: value for name, value in metadata.items() if name not in _RESERVED},
            )
        except Exception as exc:
            logger.warning("vector_upsert_failed", error_type=type(exc).__name__)

    async def search(
        self, *, user_id: UUID, query: str, limit: int, agents: Sequence[str] | None = None
    ) -> list[Memory]:
        try:
            payloads = await _search(
                user_id, query, limit=limit, agent_ids=list(agents) if agents else None
            )
        except Exception as exc:
            logger.warning("vector_search_failed", error_type=type(exc).__name__)
            return []
        return [
            Memory(
                text=str(payload.get("text", "")),
                agent=str(payload.get("agent_id", "")),
                metadata={
                    name: str(value) for name, value in payload.items() if name not in _RESERVED
                },
            )
            for payload in payloads
        ]
