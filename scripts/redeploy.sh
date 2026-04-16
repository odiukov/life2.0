#!/usr/bin/env bash
# Rebuild images and restart services. `docker compose up -d` alone does NOT
# rebuild when source changes — use this after editing code inside a service.
#
# Usage:
#   scripts/redeploy.sh                      # rebuild + restart everything
#   scripts/redeploy.sh orchestrator         # rebuild + restart one service
#   scripts/redeploy.sh agent-body telegram-bot
set -euo pipefail

cd "$(dirname "$0")/.."

./scripts/export-auth.sh

docker compose up -d --build "$@"
docker compose ps
