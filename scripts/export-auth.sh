#!/usr/bin/env bash
# Export Claude Code OAuth token from macOS Keychain to .env.auth
# Run this script before `docker compose up` or when auth expires.

set -euo pipefail

CREDS=$(security find-generic-password -s "Claude Code-credentials" -w 2>&1)
if [[ $? -ne 0 ]]; then
  echo "ERROR: Could not read Claude Code credentials from Keychain."
  echo "Make sure you are logged in to Claude Code: run 'claude' and complete login."
  exit 1
fi

ACCESS_TOKEN=$(python3 -c "import json, sys; d=json.loads(sys.stdin.read()); print(d['claudeAiOauth']['accessToken'])" <<< "$CREDS")
EXPIRES_AT=$(python3 -c "import json, sys; d=json.loads(sys.stdin.read()); print(d['claudeAiOauth']['expiresAt'])" <<< "$CREDS")
EXPIRES_HUMAN=$(python3 -c "import sys, datetime; ts=int(sys.argv[1])/1000; print(datetime.datetime.fromtimestamp(ts))" "$EXPIRES_AT")

cat > "$(dirname "$0")/../.env.auth" << EOF
ANTHROPIC_API_KEY=${ACCESS_TOKEN}
EOF

echo "✓ Token exported to .env.auth"
echo "  Expires: ${EXPIRES_HUMAN}"
echo "  Re-run this script when the token expires."
