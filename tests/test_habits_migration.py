import os
import pytest
import asyncpg


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
    }


@pytest.mark.asyncio
async def test_habits_unique_active_name_enforced():
    dsn = os.environ.get("POSTGRES_DSN")
    if not dsn:
        pytest.skip("POSTGRES_DSN not set — skipping integration test")
    conn = await asyncpg.connect(dsn)
    try:
        await conn.execute("DELETE FROM habits WHERE name LIKE 'test-unique-%'")
        await conn.execute(
            "INSERT INTO habits (name, kind, cadence_type) VALUES "
            "('test-unique-name', 'boolean', 'daily')"
        )
        with pytest.raises(asyncpg.UniqueViolationError):
            await conn.execute(
                "INSERT INTO habits (name, kind, cadence_type) VALUES "
                "('test-unique-name', 'boolean', 'daily')"
            )
        # archiving the first → second insert succeeds
        await conn.execute(
            "UPDATE habits SET archived_at = now() WHERE name = 'test-unique-name'"
        )
        await conn.execute(
            "INSERT INTO habits (name, kind, cadence_type) VALUES "
            "('test-unique-name', 'boolean', 'daily')"
        )
    finally:
        await conn.execute("DELETE FROM habits WHERE name LIKE 'test-unique-%'")
        await conn.close()
