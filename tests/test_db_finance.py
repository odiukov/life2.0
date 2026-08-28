"""Integration tests for finance DB helpers. Requires docker compose postgres up."""
from __future__ import annotations

import os
from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest

pytestmark = pytest.mark.asyncio

# Fixed test user UUID to scope all finance test rows
_TEST_USER_ID = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")


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
        # Seed the test user
        await conn.execute(
            "INSERT INTO public.users (id, name, timezone) VALUES ($1, $2, 'UTC') ON CONFLICT DO NOTHING",
            _TEST_USER_ID, "test-finance",
        )
        await conn.execute(
            "DELETE FROM finance_transactions WHERE user_id = $1 AND txn_id LIKE 'TEST_%'",
            _TEST_USER_ID,
        )
        await conn.execute(
            "DELETE FROM finance_category_cache WHERE user_id = $1 AND desc_key LIKE 'test_%'",
            _TEST_USER_ID,
        )
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(
            "DELETE FROM finance_transactions WHERE user_id = $1 AND txn_id LIKE 'TEST_%'",
            _TEST_USER_ID,
        )
        await conn.execute(
            "DELETE FROM finance_category_cache WHERE user_id = $1 AND desc_key LIKE 'test_%'",
            _TEST_USER_ID,
        )
    finally:
        await conn.close()
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


def _sample_rows():
    return [
        {
            "txn_id": "TEST_A", "ts": datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
            "direction": "IN", "amount": Decimal("100.00"), "currency": "USD",
            "description": "CLIENT PAY", "raw": {"k": "v"},
        },
        {
            "txn_id": "TEST_B", "ts": datetime(2026, 4, 2, 10, 0, tzinfo=timezone.utc),
            "direction": "OUT", "amount": Decimal("20.00"), "currency": "USD",
            "description": "UBER", "raw": {"k": "v"},
        },
    ]


async def test_upsert_finance_rows_is_idempotent():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from shared.db import upsert_finance_rows, fetch_uncategorized_ids

    inserted1, skipped1 = await upsert_finance_rows(_TEST_USER_ID, _sample_rows())
    assert inserted1 == 2 and skipped1 == 0

    inserted2, skipped2 = await upsert_finance_rows(_TEST_USER_ID, _sample_rows())
    assert inserted2 == 0 and skipped2 == 2

    ids = await fetch_uncategorized_ids(_TEST_USER_ID)
    # Both rows inserted have category=NULL so both should show.
    assert len(ids) >= 2


async def test_set_transaction_categories_updates_rows():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from shared.db import (
        upsert_finance_rows, fetch_uncategorized_ids, set_transaction_categories,
    )
    await upsert_finance_rows(_TEST_USER_ID, _sample_rows())
    ids = await fetch_uncategorized_ids(_TEST_USER_ID)
    updates = {tid: ("income" if tid.endswith("A") else "transport")
               for tid in ids if tid.startswith("TEST_")}
    await set_transaction_categories(_TEST_USER_ID, updates)
    after = await fetch_uncategorized_ids(_TEST_USER_ID)
    # TEST_A and TEST_B shouldn't be uncategorized anymore.
    assert not any(i in after for i in updates)


async def test_category_cache_upsert_and_get():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from shared.db import upsert_category_cache, get_category_cache

    await upsert_category_cache(_TEST_USER_ID, {"test_key_1": "food", "test_key_2": "housing"})
    hits = await get_category_cache(_TEST_USER_ID, ["test_key_1", "test_key_2", "test_missing"])
    assert hits == {"test_key_1": "food", "test_key_2": "housing"}


async def test_finance_rows_for_month_filters_range():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from shared.db import upsert_finance_rows, finance_rows_for_month
    await upsert_finance_rows(_TEST_USER_ID, _sample_rows())
    rows = await finance_rows_for_month(_TEST_USER_ID, "2026-04")
    test_ids = [r["txn_id"] for r in rows if r["txn_id"].startswith("TEST_")]
    assert "TEST_A" in test_ids and "TEST_B" in test_ids

    rows_mar = await finance_rows_for_month(_TEST_USER_ID, "2026-03")
    assert not any(r["txn_id"].startswith("TEST_") for r in rows_mar)
