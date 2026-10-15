#!/usr/bin/env bash
# Exercise the tenant-scoped vector adapter against Qdrant and Gemini.
set -euo pipefail
cd "$(dirname "$0")/.."

if [[ -f .env ]]; then
  set -a
  source .env
  set +a
fi
: "${GEMINI_API_KEY:?Configure GEMINI_API_KEY before the vector smoke test}"
export QDRANT_HOST="${QDRANT_HOST_OVERRIDE:-localhost}"

uv run python - <<'PY'
import asyncio
import json
import sys
from uuid import uuid4

from qdrant_client.models import PointIdsList
from shared.adapters.vector import COLLECTION, QdrantVectorMemory, _get_client, _point_id


async def main() -> None:
    owner, other = uuid4(), uuid4()
    key = f"smoke-{uuid4()}"
    text = f"vector memory smoke sentinel {key}"
    identity = json.dumps([str(owner), "sleep", key], separators=(",", ":"))
    memory = QdrantVectorMemory()
    try:
        await memory.upsert(user_id=owner, agent="sleep", key=key, text=text, metadata={"smoke_id": key})
        own = await memory.search(user_id=owner, query=text, limit=10, agents=["sleep"])
        if not any(item.metadata.get("smoke_id") == key for item in own):
            raise RuntimeError("vector_owner_search_failed")
        foreign = await memory.search(user_id=other, query=text, limit=10, agents=["sleep"])
        if any(item.metadata.get("smoke_id") == key for item in foreign):
            raise RuntimeError("vector_tenant_isolation_failed")
        print("PASS vector owner search")
        print("PASS vector tenant isolation")
    finally:
        try:
            await _get_client().delete(
                collection_name=COLLECTION,
                points_selector=PointIdsList(points=[_point_id(identity)]),
            )
        except Exception:
            raise RuntimeError("vector_cleanup_failed") from None


try:
    asyncio.run(main())
except Exception as exc:
    print(f"FAIL vector_smoke error_type={type(exc).__name__}", file=sys.stderr)
    sys.exit(1)
PY
