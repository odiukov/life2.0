"""Pure-function parser for Payoneer CSV exports.

Header fingerprint is pinned against a synthetic sample; real Payoneer header
replaces it in a follow-up commit once user supplies a sanitized export
(spec §9). Kept free of DB + LLM so parser stays trivially testable.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


class PayoneerCsvFormatError(ValueError):
    """Raised when the CSV header does not match the expected Payoneer shape."""


_EXPECTED_HEADER = [
    "Transaction ID",
    "Date",
    "Type",
    "Description",
    "Currency",
    "Amount",
    "Status",
]


def _parse_amount(raw: str) -> Decimal:
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    return Decimal(cleaned)


def _parse_ts(raw: str) -> datetime:
    # Synthetic fixture uses "YYYY-MM-DD HH:MM:SS"; treat as UTC until the real
    # header is pinned. If real CSV ships different TZ conventions, this parser
    # is the one place to adjust.
    dt = datetime.strptime(raw.strip(), "%Y-%m-%d %H:%M:%S")
    return dt.replace(tzinfo=timezone.utc)


def parse_payoneer_csv(raw: bytes) -> tuple[list[dict[str, Any]], int]:
    """Parse a Payoneer CSV export. Return (rows, skipped_count).

    Raises PayoneerCsvFormatError if the header doesn't match
    `_EXPECTED_HEADER`. Skips individual malformed rows (missing txn_id,
    unparseable amount, etc.) and reports the count.
    """
    text = raw.decode("utf-8-sig", errors="replace")
    reader = csv.reader(io.StringIO(text))

    try:
        header = next(reader)
    except StopIteration:
        raise PayoneerCsvFormatError("empty CSV")

    header_norm = [h.strip() for h in header]
    if header_norm != _EXPECTED_HEADER:
        raise PayoneerCsvFormatError(
            f"unexpected header: got {header_norm}, expected {_EXPECTED_HEADER}"
        )

    rows: list[dict[str, Any]] = []
    skipped = 0

    for cells in reader:
        if len(cells) != len(_EXPECTED_HEADER):
            skipped += 1
            continue
        raw_row = dict(zip(_EXPECTED_HEADER, [c.strip() for c in cells]))
        txn_id = raw_row["Transaction ID"]
        if not txn_id:
            skipped += 1
            continue
        try:
            amount = _parse_amount(raw_row["Amount"])
            ts = _parse_ts(raw_row["Date"])
        except (InvalidOperation, ValueError):
            skipped += 1
            continue

        direction = "IN" if amount >= 0 else "OUT"
        rows.append({
            "txn_id": txn_id,
            "ts": ts,
            "direction": direction,
            "amount": abs(amount),
            "currency": raw_row["Currency"],
            "description": raw_row["Description"],
            "raw": raw_row,
        })

    return rows, skipped
