"""Payoneer PDF parser — unit tests on synthetic text + a round-trip PDF.

The structural unit tests call `_parse_text` directly so we can cover edge
cases (multi-page line stream, footer skip, malformed row, unknown header)
without pymupdf round-trip overhead. One integration test builds a real PDF
from synthetic text via pymupdf at runtime — ensures the public
`parse_payoneer_pdf(raw: bytes)` path wires up end-to-end with the actual
library that production uses.
"""
from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

import pytest

from orchestrator.app.payoneer_pdf import (
    PayoneerPdfFormatError,
    parse_payoneer_pdf,
    _parse_text,
)


_SYNTHETIC_PAGE_1 = """\
Account Statement
Jane Doe
Account
EUR balance
Some Street 1
Period
03/01/2026 - 03/31/2026
Somewhere
Issuing Date
04/01/2026
380000000000
Date
Description
Amount
Currency
Running Balance
31 Mar, 2026
Card charge (MERCHANT A)
-44.00
EUR
445.89
30 Mar, 2026
Card charge (MERCHANT B)
-6.95
EUR
489.89
28 Mar, 2026
Transfer between balances - to EUR from USD
572.44
EUR
764.29
© 2005-2026 Payoneer, All Rights Reserved   |   www.payoneer.com
"""


_SYNTHETIC_PAGE_2 = """\
26 Mar, 2026
Card charge (MERCHANT C)
-36.20
EUR
191.85
25 Mar, 2026
Card charge (MERCHANT D)
-26.90
EUR
277.25
© 2005-2026 Payoneer, All Rights Reserved   |   www.payoneer.com
"""


def _two_page_text() -> str:
    return _SYNTHETIC_PAGE_1 + _SYNTHETIC_PAGE_2


# ---------- _parse_text: structural ------------------------------------------

def test_parse_text_happy_path():
    rows, skipped = _parse_text(_two_page_text())
    assert skipped == 0
    assert len(rows) == 5
    txn_ids = [r["txn_id"] for r in rows]
    # Deterministic and distinct
    assert len(set(txn_ids)) == 5
    assert all(t.startswith("pyn-pdf-") for t in txn_ids)


def test_parse_text_direction_and_amount_sign():
    rows, _ = _parse_text(_two_page_text())
    by_desc = {r["description"]: r for r in rows}
    # Negative amounts (OUT)
    assert by_desc["Card charge (MERCHANT A)"]["direction"] == "OUT"
    assert by_desc["Card charge (MERCHANT A)"]["amount"] == Decimal("44.00")
    # Positive amount (IN)
    transfer = by_desc["Transfer between balances - to EUR from USD"]
    assert transfer["direction"] == "IN"
    assert transfer["amount"] == Decimal("572.44")


def test_parse_text_ts_is_utc():
    rows, _ = _parse_text(_two_page_text())
    ts = rows[0]["ts"]
    assert ts.tzinfo == timezone.utc
    assert ts.date().isoformat() == "2026-03-31"


def test_parse_text_currency_preserved():
    rows, _ = _parse_text(_two_page_text())
    assert all(r["currency"] == "EUR" for r in rows)


def test_parse_text_raw_preserves_running_balance_and_period():
    rows, _ = _parse_text(_two_page_text())
    r = rows[0]
    assert r["raw"]["running_balance"] == "445.89"
    assert r["raw"]["period"] == "03/01/2026 - 03/31/2026"


def test_parse_text_is_deterministic():
    rows_a, _ = _parse_text(_two_page_text())
    rows_b, _ = _parse_text(_two_page_text())
    assert [r["txn_id"] for r in rows_a] == [r["txn_id"] for r in rows_b]


def test_parse_text_different_running_balance_produces_different_id():
    """Running balance is part of the dedup key — same date/desc/amount with
    different running balance must produce different txn_ids."""
    base = _SYNTHETIC_PAGE_1
    variant = base.replace("445.89", "999.99")
    rows_a, _ = _parse_text(base)
    rows_b, _ = _parse_text(variant)
    # First row differs in running balance -> different id
    assert rows_a[0]["txn_id"] != rows_b[0]["txn_id"]


def test_parse_text_footer_lines_skipped():
    rows, skipped = _parse_text(_two_page_text())
    # The "© 2005-..." lines don't become rows and aren't counted as skipped
    # because they're filtered before grouping.
    assert skipped == 0
    assert not any("©" in r["description"] for r in rows)


def test_parse_text_unparseable_date_is_skipped():
    broken_row_text = _SYNTHETIC_PAGE_1.replace("31 Mar, 2026", "NOT A DATE")
    rows, skipped = _parse_text(broken_row_text)
    # The first row is skipped; the other two rows on page 1 still parse.
    assert skipped == 1
    assert len(rows) == 2


def test_parse_text_missing_marker_raises():
    wrong = "Some other PDF\nwith no table\nat all\n"
    with pytest.raises(PayoneerPdfFormatError):
        _parse_text(wrong)


def test_parse_text_raises_when_not_account_statement():
    wrong = (
        "Just a blank doc\n"
        "Date\nDescription\nAmount\nCurrency\nRunning Balance\n"
        "31 Mar, 2026\nX\n-1.00\nEUR\n100\n"
    )
    with pytest.raises(PayoneerPdfFormatError):
        _parse_text(wrong)


# ---------- parse_payoneer_pdf: integration via pymupdf ----------------------

def _build_fake_pdf(text_pages: list[str]) -> bytes:
    """Render text pages into a minimal PDF with pymupdf so we exercise the
    get_text() path that production uses."""
    import pymupdf
    doc = pymupdf.open()
    for text in text_pages:
        page = doc.new_page(width=595, height=842)
        page.insert_text((50, 50), text, fontsize=8, fontname="helv")
    out = doc.tobytes()
    doc.close()
    return out


def test_parse_payoneer_pdf_round_trip_through_pymupdf():
    raw = _build_fake_pdf([_SYNTHETIC_PAGE_1, _SYNTHETIC_PAGE_2])
    rows, skipped = parse_payoneer_pdf(raw)
    assert skipped == 0
    assert len(rows) == 5
    txn_ids = [r["txn_id"] for r in rows]
    assert len(set(txn_ids)) == 5


def test_parse_payoneer_pdf_rejects_non_pdf_bytes():
    with pytest.raises(PayoneerPdfFormatError):
        parse_payoneer_pdf(b"not a pdf at all")
