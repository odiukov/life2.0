"""Payoneer monthly-statement PDF parser.

Structure of a Payoneer statement (as of 2026-04):
  Header block: "Account Statement" + account metadata + "Period" dates.
  Table: "Date / Description / Amount / Currency / Running Balance" marker
  followed by a stream of 5-line groups — one per transaction.
  Every page ends with a "© 2005-...Payoneer..." footer line.

No `Transaction ID` is exposed in the PDF — we derive a deterministic
synthetic id from `sha256("{period}|{date}|{desc}|{amount}|{currency}|{running_balance}")`.
Running balance is point-in-time unique per account, so the hash is stable
across re-uploads (idempotent via ON CONFLICT DO NOTHING).

The parser is split so `_parse_text` can be unit-tested directly against a
synthetic string, and `parse_payoneer_pdf(bytes)` wraps pymupdf.
"""
from __future__ import annotations

import hashlib
import io
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from typing import Any


class PayoneerPdfFormatError(ValueError):
    """Raised when the PDF doesn't look like a Payoneer Account Statement."""


_TABLE_HEADER: tuple[str, ...] = (
    "Date", "Description", "Amount", "Currency", "Running Balance",
)
_FOOTER_PREFIX = "©"
_ACCOUNT_STATEMENT_MARKER = "Account Statement"


def _clean_lines(text: str) -> list[str]:
    """Split into non-empty, stripped lines and drop footer markers."""
    out: list[str] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        if s.startswith(_FOOTER_PREFIX):
            continue
        out.append(s)
    return out


def _find_period(lines: list[str], limit: int) -> str:
    """Return the period string following the 'Period' marker, or empty."""
    for i in range(min(limit, len(lines) - 1)):
        if lines[i] == "Period":
            return lines[i + 1]
    return ""


def _find_table_start(lines: list[str]) -> int | None:
    """Return the index AFTER the 5-line table header, or None."""
    for i in range(len(lines) - len(_TABLE_HEADER) + 1):
        if tuple(lines[i:i + len(_TABLE_HEADER)]) == _TABLE_HEADER:
            return i + len(_TABLE_HEADER)
    return None


def _parse_ts(raw: str) -> datetime:
    """Payoneer prints dates as '31 Mar, 2026'. Treat as UTC midnight."""
    dt = datetime.strptime(raw.strip(), "%d %b, %Y")
    return dt.replace(tzinfo=timezone.utc)


def _parse_amount(raw: str) -> Decimal:
    cleaned = raw.replace(",", "").replace(" ", "").strip()
    return Decimal(cleaned)


def _txn_id(period: str, date_str: str, desc: str, amount: Decimal,
            currency: str, running: Decimal) -> str:
    raw_key = f"{period}|{date_str}|{desc}|{amount}|{currency}|{running}"
    digest = hashlib.sha256(raw_key.encode("utf-8")).hexdigest()[:16]
    return f"pyn-pdf-{digest}"


def _parse_text(text: str) -> tuple[list[dict[str, Any]], int]:
    """Parse the concatenated text of a Payoneer statement PDF.

    Returns (rows, skipped_count). Raises PayoneerPdfFormatError if the
    'Account Statement' marker or the table header is absent.
    """
    lines = _clean_lines(text)

    if not any(ln.startswith(_ACCOUNT_STATEMENT_MARKER) for ln in lines[:30]):
        raise PayoneerPdfFormatError(
            "missing 'Account Statement' marker — not a Payoneer PDF"
        )

    start = _find_table_start(lines)
    if start is None:
        raise PayoneerPdfFormatError(
            "table header (Date/Description/Amount/Currency/Running Balance) not found"
        )

    period = _find_period(lines, limit=start)

    rows: list[dict[str, Any]] = []
    skipped = 0

    i = start
    while i + 4 < len(lines):
        group = lines[i:i + 5]
        date_str, desc, amount_str, currency, running_str = group

        try:
            ts = _parse_ts(date_str)
        except ValueError:
            # Payoneer row layout is stable after the table header + footer
            # filter, so we treat a bad first line as a malformed *row* and
            # advance by 5 to keep alignment. If a future format change ever
            # breaks this, the integration smoke run against the real PDF
            # will surface it.
            skipped += 1
            i += 5
            continue

        try:
            amount = _parse_amount(amount_str)
            running = _parse_amount(running_str)
        except InvalidOperation:
            skipped += 1
            i += 5
            continue

        direction = "IN" if amount >= 0 else "OUT"
        abs_amount = abs(amount)

        rows.append({
            "txn_id": _txn_id(period, date_str, desc, abs_amount, currency, running),
            "ts": ts,
            "direction": direction,
            "amount": abs_amount,
            "currency": currency,
            "description": desc,
            "raw": {
                "date": date_str,
                "amount": amount_str,
                "currency": currency,
                "running_balance": running_str,
                "period": period,
            },
        })
        i += 5

    return rows, skipped


def parse_payoneer_pdf(raw: bytes) -> tuple[list[dict[str, Any]], int]:
    """Public entry: bytes → (rows, skipped)."""
    import pymupdf

    try:
        doc = pymupdf.open(stream=raw, filetype="pdf")
    except Exception as e:
        raise PayoneerPdfFormatError(f"cannot open as PDF: {e}") from e

    try:
        text = "\n".join(page.get_text() for page in doc)
    finally:
        doc.close()

    return _parse_text(text)
