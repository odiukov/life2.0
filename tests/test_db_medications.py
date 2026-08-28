"""Integration test — requires docker compose postgres up.
Uses POSTGRES_DSN env var set in .env or falls back to localhost."""
import os
import pytest
from uuid import UUID

pytestmark = pytest.mark.asyncio

from shared.db import (
    insert_medication,
    fetch_active_medications,
    archive_medication,
    find_medication_by_name,
)

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
            _TEST_USER_ID, "test-medications",
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


async def test_insert_and_fetch():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    mid = await insert_medication(
        _TEST_USER_ID, name="magnesium", dose="200mg", schedule="daily 21:00", notes=None,
    )
    assert mid
    meds = await fetch_active_medications(_TEST_USER_ID)
    assert any(m["id"] == mid and m["name"] == "magnesium" for m in meds)
    await archive_medication(_TEST_USER_ID, mid)


async def test_find_by_name_canonicalizes():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    mid = await insert_medication(
        _TEST_USER_ID, name="vitamin-d", dose="2000IU", schedule="daily morning", notes=None,
    )
    found = await find_medication_by_name(_TEST_USER_ID, "Vitamin D")  # different case + space
    assert found is not None and found["id"] == mid
    await archive_medication(_TEST_USER_ID, mid)


async def test_archive_soft_deletes():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    mid = await insert_medication(
        _TEST_USER_ID, name="zinc", dose="15mg", schedule="daily evening", notes=None,
    )
    ok = await archive_medication(_TEST_USER_ID, mid)
    assert ok is True
    active = await fetch_active_medications(_TEST_USER_ID)
    assert not any(m["id"] == mid for m in active)


async def test_duplicate_active_name_raises():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    import asyncpg
    mid = await insert_medication(
        _TEST_USER_ID, name="iron", dose="18mg", schedule="daily morning", notes=None,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert_medication(
            _TEST_USER_ID, name="iron", dose="25mg", schedule="daily evening", notes=None,
        )
    await archive_medication(_TEST_USER_ID, mid)
