"""Integration test — requires docker compose postgres up.
Uses POSTGRES_DSN env var set in .env or falls back to localhost."""

import os
import pytest
from uuid import UUID

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]

from shared.db import fetch_active_medications, get_pool

# Fixed test user UUID to scope all medication test rows
_TEST_USER_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


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

    import asyncpg

    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        # Seed the test user
        await conn.execute(
            "INSERT INTO public.users (id, name, timezone) VALUES ($1, $2, 'UTC') ON CONFLICT DO NOTHING",
            _TEST_USER_ID,
            "test-medications",
        )
        await conn.execute(
            "DELETE FROM medications WHERE user_id = $1 AND name IN ('magnesium', 'vitamin-d', 'zinc', 'iron')",
            _TEST_USER_ID,
        )
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(
            "DELETE FROM medications WHERE user_id = $1 AND name IN ('magnesium', 'vitamin-d', 'zinc', 'iron')",
            _TEST_USER_ID,
        )
    finally:
        await conn.close()
    # Close pool again after test so the next test's setup starts clean.
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


async def test_fetch_active_medications_excludes_archived():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    pool = await get_pool()
    mid = await pool.fetchval(
        "INSERT INTO medications (user_id, name, dose, schedule) "
        "VALUES ($1, 'magnesium', '200mg', 'daily 21:00') RETURNING id::text",
        _TEST_USER_ID,
    )
    meds = await fetch_active_medications(_TEST_USER_ID)
    assert any(m["id"] == mid and m["name"] == "magnesium" for m in meds)
    await pool.execute("UPDATE medications SET archived_at = now() WHERE id = $1::uuid", mid)
    assert not any(m["id"] == mid for m in await fetch_active_medications(_TEST_USER_ID))
