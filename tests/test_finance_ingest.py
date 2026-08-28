"""Tests for orchestrator.app.finance_ingest.

`ingest_rows` and `categorize_new` hit the DB (integration, skipped without
POSTGRES_DSN). `build_upload_summary` is pure and runs unconditionally.
"""
from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from decimal import Decimal
from unittest.mock import AsyncMock, MagicMock, patch
from uuid import UUID

import pytest

# Fixed test user UUID to scope all finance ingest test rows
_TEST_USER_ID = UUID("ffffffff-ffff-ffff-ffff-ffffffffffff")


def _has_db() -> bool:
    return bool(os.environ.get("POSTGRES_DSN"))


# ---------- build_upload_summary: pure ---------------------------------------

def test_build_upload_summary_happy_path():
    from orchestrator.app.finance_ingest import build_upload_summary
    s = build_upload_summary(
        inserted=12, skipped=3,
        income_by_currency={"USD": Decimal("2500.00"), "EUR": Decimal("300.00")},
        spending_by_currency={"USD": Decimal("1820.00")},
        top_categories=[("software", Decimal("420.00"), "USD"),
                        ("food", Decimal("340.00"), "USD"),
                        ("subscriptions", Decimal("290.00"), "USD")],
    )
    assert "12 новых" in s and "3 пропущено" in s
    assert "+$2 500.00 USD" in s or "+$2500.00 USD" in s or "2500" in s
    assert "+€300" in s or "300" in s
    assert "software" in s and "food" in s and "subscriptions" in s


def test_build_upload_summary_zero_new():
    from orchestrator.app.finance_ingest import build_upload_summary
    s = build_upload_summary(
        inserted=0, skipped=0,
        income_by_currency={}, spending_by_currency={}, top_categories=[],
    )
    assert "0 новых" in s


# ---------- categorize_new: DB + LLM (mocked) --------------------------------

pytestmark = pytest.mark.asyncio  # async tests below


async def _seed_row(txn_id: str, description: str):
    from shared.db import upsert_finance_rows
    await upsert_finance_rows(_TEST_USER_ID, [{
        "txn_id": txn_id,
        "ts": datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
        "direction": "OUT",
        "amount": Decimal("10.00"),
        "currency": "USD",
        "description": description,
        "raw": {},
    }])


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
        # Seed test user
        await conn.execute(
            "INSERT INTO public.users (id, name, timezone) VALUES ($1, $2, 'UTC') ON CONFLICT DO NOTHING",
            _TEST_USER_ID, "test-finance-ingest",
        )
        await conn.execute(
            "DELETE FROM finance_transactions WHERE user_id = $1 AND txn_id LIKE 'INGEST_%'",
            _TEST_USER_ID,
        )
        await conn.execute(
            "DELETE FROM finance_category_cache WHERE user_id = $1 AND (desc_key LIKE '%uber%' OR desc_key LIKE '%spotify%')",
            _TEST_USER_ID,
        )
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(
            "DELETE FROM finance_transactions WHERE user_id = $1 AND txn_id LIKE 'INGEST_%'",
            _TEST_USER_ID,
        )
        await conn.execute(
            "DELETE FROM finance_category_cache WHERE user_id = $1 AND (desc_key LIKE '%uber%' OR desc_key LIKE '%spotify%')",
            _TEST_USER_ID,
        )
    finally:
        await conn.close()
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


def _fake_llm(payload: dict):
    mock = MagicMock()
    mock.ainvoke = AsyncMock(return_value=MagicMock(content=json.dumps(payload)))
    return mock


async def test_categorize_new_uses_cache_hit():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app.finance_ingest import categorize_new
    from shared.db import upsert_category_cache

    await _seed_row("INGEST_1", "UBER TRIP 2026-04-01")
    await upsert_category_cache(_TEST_USER_ID, {"uber-trip": "transport"})

    fake = _fake_llm({})
    with patch("orchestrator.app.finance_ingest._get_llm", return_value=fake):
        await categorize_new(_TEST_USER_ID, ["INGEST_1"])

    # LLM should NOT have been invoked because cache hit.
    fake.ainvoke.assert_not_awaited()

    import asyncpg
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        row = await conn.fetchrow(
            "SELECT category FROM finance_transactions WHERE user_id = $1 AND txn_id = $2",
            _TEST_USER_ID, "INGEST_1",
        )
    finally:
        await conn.close()
    assert row["category"] == "transport"


async def test_categorize_new_invokes_llm_on_miss():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app.finance_ingest import categorize_new, _desc_key

    await _seed_row("INGEST_2", "SPOTIFY MONTHLY")
    key = _desc_key("SPOTIFY MONTHLY")

    fake = _fake_llm({key: "subscriptions"})
    with patch("orchestrator.app.finance_ingest._get_llm", return_value=fake):
        await categorize_new(_TEST_USER_ID, ["INGEST_2"])

    fake.ainvoke.assert_awaited()

    import asyncpg
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        row = await conn.fetchrow(
            "SELECT category FROM finance_transactions WHERE user_id = $1 AND txn_id = $2",
            _TEST_USER_ID, "INGEST_2",
        )
        cache = await conn.fetchrow(
            "SELECT category FROM finance_category_cache WHERE user_id = $1 AND desc_key = $2",
            _TEST_USER_ID, key,
        )
    finally:
        await conn.close()
    assert row["category"] == "subscriptions"
    assert cache["category"] == "subscriptions"


async def test_categorize_new_llm_failure_leaves_null():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app.finance_ingest import categorize_new

    await _seed_row("INGEST_3", "MYSTERY PAYMENT")

    broken = MagicMock()
    broken.ainvoke = AsyncMock(side_effect=RuntimeError("LLM boom"))
    with patch("orchestrator.app.finance_ingest._get_llm", return_value=broken):
        await categorize_new(_TEST_USER_ID, ["INGEST_3"])  # must not raise

    import asyncpg
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        row = await conn.fetchrow(
            "SELECT category FROM finance_transactions WHERE user_id = $1 AND txn_id = $2",
            _TEST_USER_ID, "INGEST_3",
        )
    finally:
        await conn.close()
    assert row["category"] is None


async def test_categorize_new_invalid_json_leaves_null():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app.finance_ingest import categorize_new

    await _seed_row("INGEST_4", "WEIRD MERCHANT")

    bad = MagicMock()
    bad.ainvoke = AsyncMock(return_value=MagicMock(content="NOT JSON <<<"))
    with patch("orchestrator.app.finance_ingest._get_llm", return_value=bad):
        await categorize_new(_TEST_USER_ID, ["INGEST_4"])  # must not raise

    import asyncpg
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        row = await conn.fetchrow(
            "SELECT category FROM finance_transactions WHERE user_id = $1 AND txn_id = $2",
            _TEST_USER_ID, "INGEST_4",
        )
    finally:
        await conn.close()
    assert row["category"] is None


# ---------- ingest_rows --------------------------------------------------------

async def test_ingest_rows_returns_inserted_and_uncategorized():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from orchestrator.app.finance_ingest import ingest_rows
    rows = [
        {"txn_id": "INGEST_A", "ts": datetime(2026, 4, 1, 9, 0, tzinfo=timezone.utc),
         "direction": "IN", "amount": Decimal("10"), "currency": "USD",
         "description": "x", "raw": {}},
    ]
    result = await ingest_rows(_TEST_USER_ID, rows)
    assert result["inserted"] == 1
    assert "INGEST_A" in result["uncategorized_ids"]

    # Re-ingest is idempotent.
    result2 = await ingest_rows(_TEST_USER_ID, rows)
    assert result2["inserted"] == 0
