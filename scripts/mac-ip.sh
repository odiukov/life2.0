#!/usr/bin/env bash
# Prints the Mac's primary LAN IPv4 — use on the developer's Mac to populate
# EXPO_PUBLIC_API_BASE_URL when testing on a physical phone.
set -euo pipefail
IP=$(ipconfig getifaddr en0 2>/dev/null || ipconfig getifaddr en1 2>/dev/null || true)
if [ -z "$IP" ]; then
  echo "Could not determine LAN IP on en0/en1. Check 'ifconfig'." >&2
  exit 1
fi
echo "$IP"
