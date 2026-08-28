import os
import pytest
import asyncpg

from tests.conftest import TEST_USER_ID, ensure_test_user

from agents.medication.app.registry import (
    create, list_active, find_by_name, archive, normalize_name,
)


def _has_db() -> bool:
    return bool(os.environ.get("POSTGRES_DSN"))


def test_normalize_name_kebabs():
    assert normalize_name("Vitamin D") == "vitamin-d"
    assert normalize_name("  IRON ") == "iron"
    assert normalize_name("") == ""
    assert normalize_name("омега-3 рыбий жир") == "омега-3-рыбий-жир"  # keeps unicode


@pytest.fixture(autouse=True)
async def _cleanup():
    if not _has_db():
        yield
        return
    import shared.db as _sdb
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None

    await ensure_test_user()

    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(
            "DELETE FROM medications WHERE user_id = $1 AND name LIKE '%magnesium%'",
            TEST_USER_ID,
        )
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(
            "DELETE FROM medications WHERE user_id = $1 AND name LIKE '%magnesium%'",
            TEST_USER_ID,
        )
    finally:
        await conn.close()
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


@pytest.mark.asyncio
async def test_create_then_find_then_archive():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    mid = await create(
        TEST_USER_ID,
        name="Magnesium",
        dose="200mg",
        schedule="daily 21:00",
        notes=None,
    )
    got = await find_by_name(TEST_USER_ID, "magnesium")
    assert got is not None and got["id"] == mid
    actives = await list_active(TEST_USER_ID)
    assert any(a["id"] == mid for a in actives)
    assert await archive(TEST_USER_ID, mid) is True
    assert (await find_by_name(TEST_USER_ID, "magnesium")) is None
