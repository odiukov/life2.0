from datetime import UTC, datetime
from decimal import Decimal
from zoneinfo import ZoneInfo

import pytest
from finance.domain.categories import CATEGORIES, desc_key
from finance.domain.figures import (
    Transaction,
    balance,
    income,
    month_bounds,
    month_of,
    runway,
    spending,
    spending_by_category,
)
from finance.domain.money import format_amount
from finance.domain.statement import NotAStatement, parse_statement_text
from finance_fixtures import NOT_A_STATEMENT, STATEMENT

KYIV = ZoneInfo("Europe/Kyiv")


def test_parses_rows_and_skips_the_broken_one() -> None:
    parsed = parse_statement_text(STATEMENT)
    assert parsed.skipped == 1
    assert [(r.direction, r.amount, r.description) for r in parsed.rows] == [
        ("IN", Decimal("4000.00"), "Client payment ACME"),
        ("OUT", Decimal("1200.00"), "Rent October"),
        ("OUT", Decimal("45.50"), "Pingo Doce 1234"),
        ("OUT", Decimal("15.99"), "Netflix 9981"),
    ]
    assert parsed.rows[0].ts == datetime(2026, 10, 1, tzinfo=UTC)


def test_transaction_ids_are_stable_and_distinct() -> None:
    first, second = parse_statement_text(STATEMENT), parse_statement_text(STATEMENT)
    assert [r.txn_id for r in first.rows] == [r.txn_id for r in second.rows]
    assert len({r.txn_id for r in first.rows}) == 4
    assert all(r.txn_id.startswith("pyn-pdf-") for r in first.rows)


@pytest.mark.parametrize("text", [NOT_A_STATEMENT, "Account Statement\nno table here\n", ""])
def test_other_documents_are_not_statements(text: str) -> None:
    with pytest.raises(NotAStatement):
        parse_statement_text(text)


def test_description_keys_ignore_numbers_and_case() -> None:
    assert desc_key("Pingo Doce 1234") == desc_key("PINGO DOCE 98-77") == "pingo-doce"
    assert desc_key("") == "__empty__"
    assert "income" in CATEGORIES
    assert CATEGORIES[-1] == "other"


def _tx(
    day: int, direction: str, amount: str, category: str | None, currency: str = "USD"
) -> Transaction:
    return Transaction(
        txn_id=f"t{day}{direction}{amount}",
        ts=datetime(2026, 10, day, 10, tzinfo=UTC),
        direction=direction,  # type: ignore[arg-type]
        amount=Decimal(amount),
        currency=currency,
        description="x",
        category=category,
    )


ROWS = [
    _tx(1, "IN", "4000.00", "income"),
    _tx(3, "OUT", "1200.00", "housing"),
    _tx(8, "OUT", "45.50", "food"),
    _tx(12, "OUT", "32.40", "food"),
    _tx(13, "OUT", "10.00", None),
    _tx(13, "OUT", "5.00", "food", currency="EUR"),
]


def test_figures_per_currency_without_conversion() -> None:
    assert income(ROWS) == {"USD": Decimal("4000.00")}
    assert spending(ROWS) == {"USD": Decimal("1287.90"), "EUR": Decimal("5.00")}
    assert spending_by_category(ROWS) == [
        ("housing", "USD", Decimal("1200.00")),
        ("food", "USD", Decimal("77.90")),
        ("food", "EUR", Decimal("5.00")),
    ]
    assert balance(ROWS) == {"USD": Decimal("2712.10"), "EUR": Decimal("-5.00")}


def test_runway_uses_the_window_average() -> None:
    result = runway(ROWS, ROWS, window_days=30)
    assert result["USD"].avg_daily_burn == Decimal("42.93")
    assert result["USD"].days == 63
    assert runway([_tx(1, "IN", "10.00", "income")], [], 30)["USD"].days is None


def test_months_follow_the_users_zone() -> None:
    late = datetime(2026, 10, 31, 22, 30, tzinfo=UTC)  # 01:30 on 1 Nov in Kyiv
    assert month_of(late, KYIV) == "2026-11"
    assert month_of(late, ZoneInfo("UTC")) == "2026-10"
    start, end = month_bounds("2026-11", KYIV)
    assert start == datetime(2026, 10, 31, 22, tzinfo=UTC)
    assert end == datetime(2026, 11, 30, 22, tzinfo=UTC)


def test_amount_formatting_matches_the_legacy_summary() -> None:
    assert format_amount("USD", Decimal("4000"), sign="+") == "+$4 000.00 USD"
    assert format_amount("UAH", Decimal("1234.5")) == "1 234.50 UAH"
