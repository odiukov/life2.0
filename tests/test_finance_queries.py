"""Integration tests for orchestrator.app.finance_queries (pure SQL)."""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

pytestmark = pytest.mark.asyncio


def _has_db() -> bool:
    return bool(os.environ.get("POSTGRES_DSN"))


@pytest.fixture(autouse=True)
async def _cleanup():
    if not _has_db():
        yield
        return
    import shared.db as _sdb
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None
    import asyncpg
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM finance_transactions WHERE txn_id LIKE 'QRY_%'")
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM finance_transactions WHERE txn_id LIKE 'QRY_%'")
    finally:
        await conn.close()
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


async def _seed():
    """Seed 4 rows into the DB for query tests — two incomes, two expenses."""
    from shared.db import upsert_finance_rows, set_transaction_categories
    base = datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc)
    await upsert_finance_rows([
        {"txn_id": "QRY_IN_1", "ts": base, "direction": "IN",
         "amount": Decimal("1000"), "currency": "USD", "description": "CLIENT A", "raw": {}},
        {"txn_id": "QRY_IN_2", "ts": base + timedelta(days=1), "direction": "IN",
         "amount": Decimal("200"), "currency": "EUR", "description": "CLIENT B", "raw": {}},
        {"txn_id": "QRY_OUT_1", "ts": base + timedelta(days=2), "direction": "OUT",
         "amount": Decimal("50"), "currency": "USD", "description": "UBER", "raw": {}},
        {"txn_id": "QRY_OUT_2", "ts": base + timedelta(days=3), "direction": "OUT",
         "amount": Decimal("30"), "currency": "USD", "description": "SPOTIFY", "raw": {}},
    ])
    await set_transaction_categories({
        "QRY_IN_1": "income",
        "QRY_IN_2": "income",
        "QRY_OUT_1": "transport",
        "QRY_OUT_2": "subscriptions",
    })


async def test_income_for_month_sums_per_currency():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    await _seed()
    from orchestrator.app.finance_queries import income_for_month
    result = await income_for_month("2026-04")
    assert result["USD"] == Decimal("1000.00")
    assert result["EUR"] == Decimal("200.00")


async def test_income_for_month_empty_on_no_data():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app.finance_queries import income_for_month
    result = await income_for_month("2026-03")
    assert result == {}


async def test_spending_by_category_ignores_incomes_and_null():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    await _seed()
    from orchestrator.app.finance_queries import spending_by_category
    result = await spending_by_category("2026-04")
    cats = {name for name, _c, _amt in result}
    assert "income" not in cats
    assert "transport" in cats and "subscriptions" in cats
    totals = {f"{n}:{c}": a for n, c, a in result}
    assert totals["transport:USD"] == Decimal("50.00")


async def test_current_balance_per_currency():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    await _seed()
    from orchestrator.app.finance_queries import current_balance
    result = await current_balance()
    assert result["USD"] == Decimal("920.00")  # 1000 − 50 − 30
    assert result["EUR"] == Decimal("200.00")


async def test_runway_computes_days_from_avg_burn():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    await _seed()
    from orchestrator.app.finance_queries import runway
    result = await runway(avg_window_days=365)  # wide window so seeded rows count
    usd = result.get("USD")
    assert usd is not None
    assert usd["balance"] == Decimal("920.00")
    assert usd["avg_daily_burn"] > 0
    assert isinstance(usd["days"], (int, float))


async def test_runway_days_none_when_no_spending():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from shared.db import upsert_finance_rows, set_transaction_categories
    await upsert_finance_rows([{
        "txn_id": "QRY_IN_ONLY",
        "ts": datetime(2026, 4, 10, 9, 0, tzinfo=timezone.utc),
        "direction": "IN", "amount": Decimal("500"), "currency": "USD",
        "description": "Z", "raw": {},
    }])
    await set_transaction_categories({"QRY_IN_ONLY": "income"})
    from orchestrator.app.finance_queries import runway
    result = await runway(avg_window_days=30)
    assert result["USD"]["days"] is None
