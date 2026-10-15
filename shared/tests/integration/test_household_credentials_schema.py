"""household_credentials: household RLS, app_rw only, and the c0008 move of per-user HA rows."""

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared.schema.migrate import upgrade
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def _household(conn, user) -> object:
    await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
    return (await conn.execute(text("SELECT household_ensure('h', 'UTC')"))).scalar_one()


async def test_rows_are_visible_only_inside_the_household(clean_db: PostgresUrls) -> None:
    a, b = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    rw = create_async_engine(clean_db.rw)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name) VALUES (:a, 'a'), (:b, 'b')"), {"a": a, "b": b}
        )
    async with rw.begin() as conn:
        house_a = await _household(conn, a)
        await conn.execute(
            text(
                "INSERT INTO household_credentials (household_id, service, payload_enc, updated_by) VALUES (:h, 'ha', '\\x01'::bytea, :u)"
            ),
            {"h": house_a, "u": a},
        )
    async with rw.begin() as conn:
        await _household(conn, b)
        assert (
            await conn.execute(text("SELECT count(*) FROM household_credentials"))
        ).scalar_one() == 0
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    "INSERT INTO household_credentials (household_id, service, payload_enc) VALUES (:h, 'ha', '\\x02'::bytea)"
                ),
                {"h": house_a},
            )
    await rw.dispose()
    await admin.dispose()


async def test_c0008_moves_per_user_ha_rows_to_the_household(clean_db: PostgresUrls) -> None:
    from alembic import command
    from shared.schema.migrate import alembic_config

    a = uuid4()
    await asyncio.to_thread(command.downgrade, alembic_config(clean_db.owner), "c0007_auth")
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.begin() as conn:
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:a, 'a')"), {"a": a})
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
            house = (await conn.execute(text("SELECT household_ensure('h', 'UTC')"))).scalar_one()
            await conn.execute(
                text(
                    "INSERT INTO integrations_credentials (user_id, service, payload_enc) VALUES (:a, 'ha', '\\xdeadbeef'::bytea)"
                ),
                {"a": a},
            )
        await asyncio.to_thread(upgrade, clean_db.owner)
        async with admin.begin() as conn:
            moved = (
                await conn.execute(
                    text(
                        "SELECT household_id, payload_enc, updated_by, version FROM household_credentials"
                    )
                )
            ).one()
            left = (
                await conn.execute(
                    text("SELECT count(*) FROM integrations_credentials WHERE service = 'ha'")
                )
            ).scalar_one()
        assert (moved.household_id, bytes(moved.payload_enc), moved.updated_by, moved.version) == (
            house,
            b"\xde\xad\xbe\xef",
            a,
            1,
        )
        assert left == 0
    finally:
        await asyncio.to_thread(upgrade, clean_db.owner)
        await admin.dispose()


async def test_c0008_refuses_plaintext_ha_rows(clean_db: PostgresUrls) -> None:
    from alembic import command
    from shared.schema.migrate import alembic_config

    a = uuid4()
    await asyncio.to_thread(command.downgrade, alembic_config(clean_db.owner), "c0007_auth")
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.begin() as conn:
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:a, 'a')"), {"a": a})
            await conn.execute(
                text(
                    "INSERT INTO integrations_credentials (user_id, service, payload_dev) VALUES (:a, 'ha', '{}'::jsonb)"
                ),
                {"a": a},
            )
        with pytest.raises(DBAPIError, match="sync-reencrypt"):
            await asyncio.to_thread(upgrade, clean_db.owner)
        async with admin.begin() as conn:
            await conn.execute(text("DELETE FROM integrations_credentials"))
    finally:
        await asyncio.to_thread(upgrade, clean_db.owner)
        await admin.dispose()


async def test_legacy_role_has_no_credential_access(clean_db: PostgresUrls) -> None:
    legacy = create_async_engine(clean_db.legacy)
    try:
        async with legacy.begin() as conn:
            with pytest.raises(DBAPIError, match="permission denied"):
                await conn.execute(text("SELECT * FROM household_credentials"))
    finally:
        await legacy.dispose()


async def test_c0008_preserves_credentials_for_users_without_membership(
    clean_db: PostgresUrls,
) -> None:
    from alembic import command
    from shared.schema.migrate import alembic_config

    user = uuid4()
    admin = create_async_engine(clean_db.admin)
    await asyncio.to_thread(command.downgrade, alembic_config(clean_db.owner), "c0007_auth")
    try:
        async with admin.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id, name, timezone) VALUES (:u, 'Ana', 'Europe/Lisbon')"),
                {"u": user},
            )
            await conn.execute(
                text(
                    "INSERT INTO integrations_credentials (user_id, service, payload_enc) VALUES (:u, 'ha', '\\xdeadbeef'::bytea)"
                ),
                {"u": user},
            )
        await asyncio.to_thread(upgrade, clean_db.owner)
        async with admin.connect() as conn:
            moved = (
                await conn.execute(
                    text(
                        "SELECT c.payload_enc, c.version, c.updated_by, m.user_id, m.display_name, h.timezone FROM household_credentials c JOIN household_members m USING (household_id) JOIN households h ON h.id = c.household_id WHERE m.user_id = :u"
                    ),
                    {"u": user},
                )
            ).one()
            remaining = (
                await conn.execute(
                    text("SELECT count(*) FROM integrations_credentials WHERE service='ha'")
                )
            ).scalar_one()
        assert bytes(moved.payload_enc) == b"\xde\xad\xbe\xef"
        assert moved.version == 1
        assert moved.updated_by == moved.user_id == user
        assert moved.display_name == "Ana"
        assert moved.timezone == "Europe/Lisbon"
        assert remaining == 0
    finally:
        await asyncio.to_thread(upgrade, clean_db.owner)
        await admin.dispose()


@pytest.mark.parametrize("old_last_used", [None, datetime(2026, 10, 14, tzinfo=UTC)])
async def test_c0008_chooses_newest_connection_by_creation_time(
    clean_db: PostgresUrls, old_last_used
) -> None:
    from alembic import command
    from shared.schema.migrate import alembic_config

    older, newer = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    await asyncio.to_thread(command.downgrade, alembic_config(clean_db.owner), "c0007_auth")
    try:
        async with admin.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id, name) VALUES (:a, 'Ana'), (:b, 'Bo')"),
                {"a": older, "b": newer},
            )
            house = await _household(conn, older)
            await conn.execute(
                text(
                    "INSERT INTO household_members (household_id, user_id, role, display_name) VALUES (:h, :u, 'member', 'Bo')"
                ),
                {"h": house, "u": newer},
            )
            await conn.execute(
                text(
                    "INSERT INTO integrations_credentials (id, user_id, service, payload_enc, created_at, last_used_at) VALUES ('00000000-0000-0000-0000-000000000001', :a, 'ha', '\\x01'::bytea, '2026-10-01', CAST(:used AS timestamptz)), ('00000000-0000-0000-0000-000000000002', :b, 'ha', '\\x02'::bytea, '2026-10-10', NULL)"
                ),
                {"a": older, "b": newer, "used": old_last_used},
            )
        await asyncio.to_thread(upgrade, clean_db.owner)
        async with admin.connect() as conn:
            moved = (
                await conn.execute(
                    text(
                        "SELECT payload_enc, updated_by FROM household_credentials WHERE household_id=:h"
                    ),
                    {"h": house},
                )
            ).one()
        assert bytes(moved.payload_enc) == b"\x02"
        assert moved.updated_by == newer
    finally:
        await asyncio.to_thread(upgrade, clean_db.owner)
        await admin.dispose()
