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
