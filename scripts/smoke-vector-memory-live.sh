#!/usr/bin/env bash
# End-to-end smoke against real health_memories: writes one canary point,
# verifies search, deletes that point. Leaves health_memories in place but empty.
# Safe to run repeatedly — the canary has a deterministic id and is overwritten/cleaned each run.
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

# .env sets QDRANT_HOST=qdrant for the docker network; we run from the host.
export QDRANT_HOST="${QDRANT_HOST_OVERRIDE:-localhost}"

# shellcheck disable=SC1091
source .venv/bin/activate

python - <<'PY'
import asyncio, os, sys
from qdrant_client import AsyncQdrantClient
from qdrant_client.models import PointIdsList
from shared.vector import (
    COLLECTION, _point_id, upsert_memory, search_memories,
)

CANARY_ID = "smoke-canary"
CANARY_TEXT = "canary: плохо спал из-за кофе"

async def main() -> int:
    rc = 0
    try:
        await upsert_memory(
            agent_id="sleep",
            id_=CANARY_ID,
            text=CANARY_TEXT,
            metadata={"skill": "smoke", "canary": True},
        )
        results = await search_memories("почему плохо спал", limit=5)
        print(f"Query returned {len(results)} result(s):")
        for i, r in enumerate(results, 1):
            print(f"  {i}. [{r.get('agent_id')}] {r.get('text')}")
        if not any(r.get("text") == CANARY_TEXT for r in results):
            print("FAIL: canary text not found in search results.", file=sys.stderr)
            rc = 2
        else:
            print("OK: canary retrieved via real upsert/search path.")
    finally:
        client = AsyncQdrantClient(
            host=os.environ.get("QDRANT_HOST", "localhost"),
            port=int(os.environ.get("QDRANT_PORT", "6333")),
        )
        try:
            await client.delete(
                collection_name=COLLECTION,
                points_selector=PointIdsList(points=[_point_id(CANARY_ID)]),
            )
            print("canary deleted")
        except Exception as e:
            print(f"cleanup warning: {e}", file=sys.stderr)
        finally:
            await client.close()
    return rc

sys.exit(asyncio.run(main()))
PY
