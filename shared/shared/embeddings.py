"""Google Gemini text-embedding-004 async HTTP client.

Wraps the generativelanguage.googleapis.com embedContent endpoint.
Returns 768-dim vectors. Raises EmbeddingError on any failure.
"""
from __future__ import annotations

import os

import httpx

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
