"""Payoneer CSV parser — unit tests against a synthetic fingerprint.

Real Payoneer header is pinned in a follow-up commit once the user supplies
a sanitized export (see spec §9).
"""
from __future__ import annotations

from decimal import Decimal
from pathlib import Path

import pytest

from orchestrator.app.payoneer_csv import (
    PayoneerCsvFormatError,
    parse_payoneer_csv,
)


FIXTURE = Path(__file__).parent / "fixtures" / "payoneer_sample.csv"


def test_parses_happy_path():
    rows, skipped = parse_payoneer_csv(FIXTURE.read_bytes())
    assert skipped == 1  # the "BROKEN ROW WITHOUT COMMAS" line
    assert len(rows) == 6
    ids = [r["txn_id"] for r in rows]
    assert ids == ["TXN001", "TXN002", "TXN003", "TXN004", "TXN005", "TXN006"]


def test_direction_inferred_from_sign():
    rows, _ = parse_payoneer_csv(FIXTURE.read_bytes())
    by_id = {r["txn_id"]: r for r in rows}
    assert by_id["TXN001"]["direction"] == "IN"   # +1500.00
    assert by_id["TXN002"]["direction"] == "OUT"  # -9.99
    assert by_id["TXN005"]["direction"] == "OUT"  # -2.00 (fee)


def test_amount_is_always_positive_decimal():
    rows, _ = parse_payoneer_csv(FIXTURE.read_bytes())
    for r in rows:
        assert isinstance(r["amount"], Decimal)
        assert r["amount"] > 0


def test_currency_preserved_per_row():
    rows, _ = parse_payoneer_csv(FIXTURE.read_bytes())
    by_id = {r["txn_id"]: r for r in rows}
    assert by_id["TXN001"]["currency"] == "USD"
    assert by_id["TXN004"]["currency"] == "EUR"


def test_raw_row_preserved():
    rows, _ = parse_payoneer_csv(FIXTURE.read_bytes())
    by_id = {r["txn_id"]: r for r in rows}
    assert by_id["TXN001"]["raw"]["Description"] == "PAYMENT FROM ACME CORP"
    assert by_id["TXN001"]["raw"]["Status"] == "Completed"


def test_malformed_header_raises():
    wrong = b"Id,When,Kind,Text,Ccy,Value,State\nX,2026-04-01,Payment,x,USD,1,ok\n"
    with pytest.raises(PayoneerCsvFormatError):
        parse_payoneer_csv(wrong)


def test_row_missing_txn_id_is_skipped():
    csv = (
        b"Transaction ID,Date,Type,Description,Currency,Amount,Status\n"
        b",2026-04-01 09:00:00,Payment,NO TXN_ID,USD,100.00,Completed\n"
        b"TXN100,2026-04-02 09:00:00,Payment,OK,USD,50.00,Completed\n"
    )
    rows, skipped = parse_payoneer_csv(csv)
    assert skipped == 1
    assert len(rows) == 1
    assert rows[0]["txn_id"] == "TXN100"


def test_amount_with_comma_thousands_separator():
    csv = (
        b"Transaction ID,Date,Type,Description,Currency,Amount,Status\n"
        b"TXN200,2026-04-01 09:00:00,Payment,BIG,USD,\"1,234.56\",Completed\n"
    )
    rows, _ = parse_payoneer_csv(csv)
    assert rows[0]["amount"] == Decimal("1234.56")
    assert rows[0]["direction"] == "IN"
