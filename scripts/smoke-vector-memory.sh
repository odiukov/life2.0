#!/usr/bin/env bash
# End-to-end smoke: real Gemini + real Qdrant, throwaway `_smoke_test` collection.
# Safe to run repeatedly. Does NOT touch health_memories.
set -euo pipefail

cd "$(dirname "$0")/.."

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  if [[ -f .env ]]; then
    set -a
    # shellcheck disable=SC1091
    source .env
    set +a
  fi
fi

if [[ -z "${GEMINI_API_KEY:-}" ]]; then
  echo "GEMINI_API_KEY is not set. Add it to .env or export it." >&2
  exit 1
fi

# shellcheck disable=SC1091
source .venv/bin/activate

python - <<'PY'
import asyncio, os, sys, uuid
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PayloadSchemaType,
    PointStruct, Filter, FieldCondition, MatchAny,
)
from shared.embeddings import embed

COLLECTION = "_smoke_test"
SAMPLES = [
    ("nutrition", "кофе вечером в 22:00"),
    ("sleep", "плохо спал из-за кофе"),
    ("workout", "починил велосипед"),
]

async def main() -> int:
    client = AsyncQdrantClient(
        host=os.environ.get("QDRANT_HOST", "localhost"),
        port=int(os.environ.get("QDRANT_PORT", "6333")),
    )
    try:
        # clean slate
        existing = await client.get_collections()
        if any(c.name == COLLECTION for c in existing.collections):
            await client.delete_collection(COLLECTION)
        await client.create_collection(
            collection_name=COLLECTION,
            vectors_config=VectorParams(size=768, distance=Distance.COSINE),
        )
        await client.create_payload_index(
            collection_name=COLLECTION,
            field_name="agent_id",
            field_schema=PayloadSchemaType.KEYWORD,
        )

        # upsert 3 records
        for agent_id, text in SAMPLES:
            vec = await embed(text, task_type="retrieval_document")
            assert len(vec) == 768, f"bad dim: {len(vec)}"
            await client.upsert(
                collection_name=COLLECTION,
                points=[PointStruct(
                    id=str(uuid.uuid4()),
                    vector=vec,
                    payload={"agent_id": agent_id, "text": text},
                )],
            )

        # cross-agent query
        q = "почему плохо спал"
        qvec = await embed(q, task_type="retrieval_query")
        results = await client.query_points(
            collection_name=COLLECTION, query=qvec, limit=3, with_payload=True,
        )
        print(f"Query: {q}")
        for i, p in enumerate(results.points, 1):
            pl = p.payload or {}
            print(f"  {i}. [{pl.get('agent_id')}] score={p.score:.3f}  {pl.get('text')}")

        # sanity: the top hit should reference sleep or nutrition, not the bicycle
        top_agent = (results.points[0].payload or {}).get("agent_id")
        if top_agent not in ("sleep", "nutrition"):
            print(f"WARN: top hit was agent={top_agent!r} — embeddings may be mis-wired", file=sys.stderr)
            return 2

        print("OK: Gemini + Qdrant wired, cross-agent retrieval works.")
        return 0
    finally:
        try:
            await client.delete_collection(COLLECTION)
            print("cleaned up _smoke_test")
        except Exception as e:
            print(f"cleanup warning: {e}", file=sys.stderr)
        await client.close()

sys.exit(asyncio.run(main()))
PY
