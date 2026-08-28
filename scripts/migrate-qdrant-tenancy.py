"""One-shot: re-index existing points in Qdrant `health_memories` with user_id payload."""
from __future__ import annotations

import os
import sys

try:
    from qdrant_client import QdrantClient
    from qdrant_client.http.models import PayloadSchemaType
except ImportError:
    sys.stderr.write("qdrant-client not installed; run: pip install qdrant-client\n")
    sys.exit(1)

OWNER = os.environ.get("OWNER_USER_ID")
if not OWNER:
    sys.stderr.write("OWNER_USER_ID env var required (your Supabase auth.users UUID)\n")
    sys.exit(1)

host = os.environ.get("QDRANT_HOST", "localhost")
port = int(os.environ.get("QDRANT_PORT", "6333"))
client = QdrantClient(host=host, port=port)

COLLECTION = "health_memories"

print(f"==> Scrolling {COLLECTION} points …")
points, _ = client.scroll(collection_name=COLLECTION, with_payload=True, limit=10_000)
print(f"   found {len(points)} points; backfilling user_id = {OWNER}")

if points:
    client.set_payload(
        collection_name=COLLECTION,
        payload={"user_id": OWNER},
        points=[p.id for p in points],
    )

print("==> Ensuring KEYWORD payload index on user_id …")
try:
    client.create_payload_index(
        collection_name=COLLECTION,
        field_name="user_id",
        field_schema=PayloadSchemaType.KEYWORD,
    )
    print("   index created")
except Exception as e:
    # Qdrant raises if the index already exists; idempotent in effect
    print(f"   index probably exists already: {e.__class__.__name__}")

print("✓ Qdrant tenancy migration complete")
