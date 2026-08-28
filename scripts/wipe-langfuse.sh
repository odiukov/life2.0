#!/usr/bin/env bash
# Dev-only: tear down Langfuse volumes for clean re-bootstrap.
set -euo pipefail

echo "Stopping Langfuse services..."
docker compose stop langfuse-web langfuse-worker langfuse-postgres langfuse-clickhouse langfuse-redis langfuse-minio || true

echo "Removing Langfuse containers..."
docker compose rm -f langfuse-web langfuse-worker langfuse-postgres langfuse-clickhouse langfuse-redis langfuse-minio || true

echo "Removing Langfuse volumes..."
docker volume rm -f \
    life-agents_langfuse_postgres_data \
    life-agents_langfuse_clickhouse_data \
    life-agents_langfuse_clickhouse_logs \
    life-agents_langfuse_redis_data \
    life-agents_langfuse_minio_data

echo "Done. Next: docker compose up -d langfuse-postgres langfuse-clickhouse langfuse-redis langfuse-minio langfuse-worker langfuse-web"
