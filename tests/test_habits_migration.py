import os
import pytest
import asyncpg

from tests.conftest import TEST_USER_ID, ensure_test_user


@pytest.mark.asyncio
async def test_habits_table_exists_with_expected_columns():
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set — skipping integration test")
    conn = await asyncpg.connect(dsn)
    try:
        rows = await conn.fetch(
            "SELECT column_name, data_type FROM information_schema.columns "
            "WHERE table_name = 'habits' ORDER BY ordinal_position"
        )
    finally:
        await conn.close()
    cols = {r["column_name"] for r in rows}
    assert cols == {
        "id", "name", "kind", "cadence_type", "cadence_days",
        "target_value", "unit", "created_at", "archived_at",
        "user_id",
    }


@pytest.mark.asyncio
async def test_habits_unique_active_name_enforced():
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set — skipping integration test")
    await ensure_test_user()
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute(
            "DELETE FROM habits WHERE user_id = $1 AND name LIKE 'test-unique-%'",
            TEST_USER_ID,
        )
        await conn.execute(
            "INSERT INTO habits (user_id, name, kind, cadence_type) VALUES "
            "($1, 'test-unique-name', 'boolean', 'daily')",
            TEST_USER_ID,
        )
        # Same user_id + name + active → unique index hit.
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO habits (user_id, name, kind, cadence_type) VALUES "
                "($1, 'test-unique-name', 'boolean', 'daily')",
                TEST_USER_ID,
            )
        # Archiving the first → second insert succeeds (partial index excludes archived rows).
        await conn.execute(
            "UPDATE habits SET archived_at = now() WHERE user_id = $1 AND name = 'test-unique-name'",
            TEST_USER_ID,
        )
        await conn.execute(
            "INSERT INTO habits (user_id, name, kind, cadence_type) VALUES "
            "($1, 'test-unique-name', 'boolean', 'daily')",
            TEST_USER_ID,
        )
    finally:
        await conn.execute(
            "DELETE FROM habits WHERE user_id = $1 AND name LIKE 'test-unique-%'",
            TEST_USER_ID,
        )
        await conn.close()
