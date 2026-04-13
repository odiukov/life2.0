from qdrant_client import AsyncQdrantClient
from qdrant_client.models import Distance, VectorParams, PointStruct
import os
import hashlib

_client: AsyncQdrantClient | None = None
VECTOR_SIZE = 384  # all-MiniLM-L6-v2 compatible placeholder; we use hash-based fake embeddings for now


def _get_client() -> AsyncQdrantClient:
    global _client
    if _client is None:
        _client = AsyncQdrantClient(
            host=os.environ.get("QDRANT_HOST", "localhost"),
            port=int(os.environ.get("QDRANT_PORT", 6333)),
        )
    return _client


def _text_to_vector(text: str) -> list[float]:
    """Deterministic fake embedding for bootstrap — replace with real model later."""
    digest = hashlib.sha256(text.encode()).digest()
    floats = [b / 255.0 for b in digest]
    # Repeat to reach VECTOR_SIZE
    repeated = (floats * (VECTOR_SIZE // len(floats) + 1))[:VECTOR_SIZE]
    return repeated


async def ensure_collection(collection: str) -> None:
    client = _get_client()
    existing = await client.get_collections()
    names = [c.name for c in existing.collections]
    if collection not in names:
        await client.create_collection(
            collection_name=collection,
            vectors_config=VectorParams(size=VECTOR_SIZE, distance=Distance.COSINE),
        )


async def upsert_memory(collection: str, id_: str, text: str, metadata: dict) -> None:
    client = _get_client()
    await ensure_collection(collection)
    await client.upsert(
        collection_name=collection,
        points=[PointStruct(
            id=int(hashlib.sha256(id_.encode()).hexdigest()[:16], 16) % (2**63),
            vector=_text_to_vector(text),
            payload={"text": text, **metadata},
        )],
    )


async def search_memories(collection: str, query: str, limit: int = 5) -> list[dict]:
    client = _get_client()
    await ensure_collection(collection)
    results = await client.search(
        collection_name=collection,
        query_vector=_text_to_vector(query),
        limit=limit,
        with_payload=True,
    )
    return [r.payload for r in results]
