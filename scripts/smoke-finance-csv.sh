#!/usr/bin/env bash
# Smoke test for /finance/upload endpoint.
# Requires docker compose up -d and migration 0006 applied.

set -euo pipefail

FIXTURE="${FIXTURE:-tests/fixtures/payoneer_sample.csv}"
URL="${ORCHESTRATOR_URL:-http://localhost:8000}/finance/upload"

if [ ! -f "$FIXTURE" ]; then
    echo "missing $FIXTURE" >&2; exit 1
fi

echo "POST $URL ← $FIXTURE"
curl -sS -F "csv=@${FIXTURE}" "$URL" | python3 -m json.tool
