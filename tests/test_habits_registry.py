import os
import pytest
import asyncpg

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
        await conn.execute("DELETE FROM habits WHERE name LIKE 'reg-test-%'")
    finally:
        await conn.close()
    yield
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute("DELETE FROM habits WHERE name LIKE 'reg-test-%'")
    finally:
        await conn.close()
    # Close pool again after test so the next test's setup starts clean.
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


def test_normalize_name_kebab_case():
    from agents.habits.app.registry import normalize_name
    assert normalize_name("Cold Shower") == "cold-shower"
    assert normalize_name("  No Alcohol  ") == "no-alcohol"
    assert normalize_name("meditation") == "meditation"
    assert normalize_name("READING_BOOK") == "reading-book"
    assert normalize_name("") == ""


@pytest.mark.asyncio
async def test_upsert_and_find_by_name():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from agents.habits.app import registry
    habit_id = await registry.create(
        name="reg-test-meditation", kind="quantitative",
        cadence_type="daily", target_value=20, unit="min",
    )
    assert habit_id

    found = await registry.find_by_name("Reg-Test-Meditation")
    assert found is not None
    assert found["id"] == habit_id
    assert found["target_value"] == 20


@pytest.mark.asyncio
async def test_find_by_name_returns_none_for_unknown():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from agents.habits.app import registry
    assert await registry.find_by_name("reg-test-nonexistent") is None


@pytest.mark.asyncio
async def test_archive_hides_from_list_but_allows_recreate():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from agents.habits.app import registry
    first_id = await registry.create(
        name="reg-test-gym", kind="boolean",
        cadence_type="weekly", cadence_days=["mon", "wed", "fri"],
    )
    active = await registry.list_active()
    assert any(h["id"] == first_id for h in active)

    assert await registry.archive(first_id) is True
    active_after = await registry.list_active()
    assert not any(h["id"] == first_id for h in active_after)

    second_id = await registry.create(
        name="reg-test-gym", kind="boolean",
        cadence_type="weekly", cadence_days=["mon", "wed", "fri"],
    )
    assert second_id != first_id


@pytest.mark.asyncio
async def test_create_duplicate_active_name_raises():
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    from agents.habits.app import registry
    await registry.create(
        name="reg-test-dup", kind="boolean", cadence_type="daily",
    )
    with pytest.raises(asyncpg.UniqueViolationError):
        await registry.create(
            name="reg-test-dup", kind="boolean", cadence_type="daily",
        )
