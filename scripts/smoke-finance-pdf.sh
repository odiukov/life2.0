#!/usr/bin/env bash
# Smoke test for /finance/upload endpoint.
# Requires docker compose up -d + migration 0006 applied.
# Builds a synthetic Payoneer-shaped PDF at runtime — no real statement
# file needed on disk.

set -euo pipefail

URL="${ORCHESTRATOR_URL:-http://localhost:8000}/finance/upload"
TMP_PDF="$(mktemp -t payoneer-smoke-XXXXXX.pdf)"
trap 'rm -f "$TMP_PDF"' EXIT

# Generate a minimal PDF whose first page matches the Payoneer fingerprint.
.venv/bin/python - "$TMP_PDF" <<'PY'
import sys
import pymupdf

PAGE = """Account Statement
Smoke Tester
Account
EUR balance
Somewhere
Period
04/01/2026 - 04/30/2026
Somewhere
Issuing Date
05/01/2026
000000000000
Date
Description
Amount
Currency
Running Balance
15 Apr, 2026
Card charge (SMOKE MERCHANT)
-12.34
EUR
100.00
10 Apr, 2026
Transfer between balances - to EUR from USD
50.00
EUR
112.34
© 2005-2026 Payoneer, All Rights Reserved
"""

doc = pymupdf.open()
p = doc.new_page(width=595, height=842)
p.insert_text((50, 50), PAGE, fontsize=8, fontname="helv")
doc.save(sys.argv[1])
doc.close()
PY

echo "POST $URL ← $TMP_PDF"
curl -sS -F "csv=@${TMP_PDF};type=application/pdf" "$URL" | python3 -m json.tool
