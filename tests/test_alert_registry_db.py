"""Integration test — requires docker compose postgres up.
Uses POSTGRES_DSN env var set in .env or falls back to localhost."""
import os
import pytest
import asyncpg
from datetime import datetime, timedelta, timezone

pytestmark = pytest.mark.asyncio

from shared.db import fetch_alert_last_emitted, upsert_alert_emission


def _has_db():
    return bool(os.environ.get("POSTGRES_DSN"))


@pytest.fixture(autouse=True)
async def _cleanup():
    if not _has_db():
        yield
        return
    # Reset the shared db pool so each test gets a fresh pool bound to its
    # own event loop (asyncpg pools are not safe to reuse across loops).
    import shared.db as _sdb
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None

    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM alert_emissions WHERE rule_id LIKE 'test.rule.%'")
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM alert_emissions WHERE rule_id LIKE 'test.rule.%'")
    finally:
        await conn.close()
    # Close pool again after test so the next test's setup starts clean.
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


async def test_upsert_and_fetch_roundtrip():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    ts = datetime(2026, 4, 19, 8, 0, tzinfo=timezone.utc)
    await upsert_alert_emission("test.rule.a", ts)
    got = await fetch_alert_last_emitted("test.rule.a")
    assert got == ts


async def test_fetch_missing_returns_none():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    got = await fetch_alert_last_emitted("test.rule.nonexistent-" + str(datetime.now().timestamp()))
    assert got is None


async def test_upsert_overwrites():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    t1 = datetime(2026, 4, 19, 8, 0, tzinfo=timezone.utc)
    t2 = t1 + timedelta(hours=3)
    await upsert_alert_emission("test.rule.b", t1)
    await upsert_alert_emission("test.rule.b", t2)
    got = await fetch_alert_last_emitted("test.rule.b")
    assert got == t2
