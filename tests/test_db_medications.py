"""Integration test — requires docker compose postgres up.
Uses POSTGRES_DSN env var set in .env or falls back to localhost."""
import os
import pytest

pytestmark = pytest.mark.asyncio

from shared.db import (
    insert_medication,
    fetch_active_medications,
    archive_medication,
    find_medication_by_name,
)


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
        await conn.execute("DELETE FROM medications WHERE name IN ('magnesium', 'vitamin-d', 'zinc', 'iron')")
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM medications WHERE name IN ('magnesium', 'vitamin-d', 'zinc', 'iron')")
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
        name="magnesium", dose="200mg", schedule="daily 21:00", notes=None,
    )
    assert mid
    meds = await fetch_active_medications()
    assert any(m["id"] == mid and m["name"] == "magnesium" for m in meds)
    await archive_medication(mid)


async def test_find_by_name_canonicalizes():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    mid = await insert_medication(
        name="vitamin-d", dose="2000IU", schedule="daily morning", notes=None,
    )
    found = await find_medication_by_name("Vitamin D")  # different case + space
    assert found is not None and found["id"] == mid
    await archive_medication(mid)


async def test_archive_soft_deletes():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    mid = await insert_medication(
        name="zinc", dose="15mg", schedule="daily evening", notes=None,
    )
    ok = await archive_medication(mid)
    assert ok is True
    active = await fetch_active_medications()
    assert not any(m["id"] == mid for m in active)


async def test_duplicate_active_name_raises():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    import asyncpg
    mid = await insert_medication(
        name="iron", dose="18mg", schedule="daily morning", notes=None,
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await insert_medication(
            name="iron", dose="25mg", schedule="daily evening", notes=None,
        )
    await archive_medication(mid)
