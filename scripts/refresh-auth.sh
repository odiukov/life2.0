#!/usr/bin/env bash
# Auto-refresh Claude OAuth token and restart agent containers
# Called by launchd every 4 hours

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(dirname "$SCRIPT_DIR")"

echo "[$(date)] Refreshing Claude auth token..."
bash "$SCRIPT_DIR/export-auth.sh"

echo "[$(date)] Restarting agent containers..."
/usr/local/bin/docker compose -f "$PROJECT_DIR/docker-compose.yml" up -d agent-sleep agent-workout agent-nutrition

echo "[$(date)] Done."
