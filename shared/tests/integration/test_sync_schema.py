import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from shared.adapters.db.credentials import sql_credential_store
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.secrets import AesGcmSecretBox
from shared.config import DatabaseSettings
from shared.ports.credentials import CredentialStore, CredentialsUnreadable
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration
KEY = bytes(range(32))


async def seed_user(admin: AsyncEngine, tz: str = "UTC") -> UUID:
    user = uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:u, 'u', :tz)"),
            {"u": user, "tz": tz},
        )
    return user


async def plaintext(
    admin: AsyncEngine, user: UUID, service: str, payload: dict[str, object]
) -> None:
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO integrations_credentials (user_id, service, payload_dev) VALUES (:u, :s, CAST(:p AS jsonb))"
            ),
            {"u": user, "s": service, "p": json.dumps(payload)},
        )


@pytest.fixture
async def env(clean_db: PostgresUrls):  # type: ignore[no-untyped-def]
    admin = create_async_engine(clean_db.admin)
    rw = create_async_engine(clean_db.rw)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    yield admin, rw, engine
    for e in (admin, rw, engine):
        await e.dispose()


async def test_reading_a_plaintext_row_reseals_it(env) -> None:  # type: ignore[no-untyped-def]
    admin, _, engine = env
    user = await seed_user(admin)
    await plaintext(admin, user, "garmin", {"email": "a@b.c", "password": "pw"})
    uow = SqlUnitOfWorkFactory(
        engine, {CredentialStore: sql_credential_store(AesGcmSecretBox(KEY))}
    )
    async with uow.for_user(user) as tx:
        assert await tx.repo(CredentialStore).get(user, "garmin") == {
            "email": "a@b.c",
            "password": "pw",
        }
    async with admin.connect() as conn:
        row = (
            await conn.execute(
                text(
                    "SELECT payload_dev, payload_enc FROM integrations_credentials WHERE user_id = :u"
                ),
                {"u": user},
            )
        ).one()
    assert row.payload_dev is None
    assert row.payload_enc is not None
    assert b"pw" not in bytes(row.payload_enc)


async def test_wrong_key_is_unreadable_not_a_crash(env) -> None:  # type: ignore[no-untyped-def]
    admin, _, engine = env
    user = await seed_user(admin)
    good = SqlUnitOfWorkFactory(
        engine, {CredentialStore: sql_credential_store(AesGcmSecretBox(KEY))}
    )
    async with good.for_user(user) as tx:
        await tx.repo(CredentialStore).put(user, "yazio", {"email": "a@b.c", "password": "pw"})
    wrong = SqlUnitOfWorkFactory(
        engine, {CredentialStore: sql_credential_store(AesGcmSecretBox(bytes(32)))}
    )
    with pytest.raises(CredentialsUnreadable):
        async with wrong.for_user(user) as tx:
            await tx.repo(CredentialStore).get(user, "yazio")
    async with good.for_user(user) as tx:  # the row was not damaged
        assert (await tx.repo(CredentialStore).get(user, "yazio"))["password"] == "pw"  # type: ignore[index]


async def test_one_backend_check_and_rls(env) -> None:  # type: ignore[no-untyped-def]
    admin, _rw, engine = env
    a, b = await seed_user(admin), await seed_user(admin)
    uow = SqlUnitOfWorkFactory(
        engine, {CredentialStore: sql_credential_store(AesGcmSecretBox(KEY))}
    )
    async with uow.for_user(a) as tx:
        await tx.repo(CredentialStore).put(a, "garmin", {"email": "a@b.c", "password": "pw"})
    async with uow.for_user(b) as tx:
        assert await tx.repo(CredentialStore).get(b, "garmin") is None
    async with admin.connect() as conn:
        with pytest.raises(DBAPIError):
            await conn.execute(
                text(
                    "INSERT INTO integrations_credentials (user_id, service, payload_dev, payload_enc) "
                    "VALUES (:u, 'yazio', '{}'::jsonb, '\\x00'::bytea)"
                ),
                {"u": b},
            )


async def test_due_users_by_local_time_success_and_retry(env) -> None:  # type: ignore[no-untyped-def]
    admin, rw, _engine = env
    lisbon = await seed_user(admin, "Europe/Lisbon")
    new_york = await seed_user(admin, "America/New_York")
    synced = await seed_user(admin, "Europe/Lisbon")
    for user in (lisbon, new_york, synced):
        await plaintext(admin, user, "garmin", {"email": "x", "password": "y"})
    await plaintext(admin, lisbon, "yazio", {"email": "x", "password": "y"})
    now = datetime(2026, 10, 13, 9, 30, tzinfo=UTC)  # 10:30 Lisbon, 05:30 New York
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO integration_sync_state (user_id, service, last_attempt_at, last_success_at) VALUES (:u, 'garmin', :t, :t)"
            ),
            {"u": synced, "t": now - timedelta(hours=1)},
        )

    async def due(at: datetime) -> dict[UUID, list[str]]:
        async with rw.connect() as conn:
            rows = (
                await conn.execute(text("SELECT * FROM integration_users_due(:n, 9)"), {"n": at})
            ).all()
        return {r.user_id: sorted(r.services) for r in rows}

    assert await due(now) == {lisbon: ["garmin", "yazio"]}
    async with admin.begin() as conn:  # a failed attempt 20 minutes ago: not due again yet
        await conn.execute(
            text(
                "INSERT INTO integration_sync_state (user_id, service, last_attempt_at, last_error) VALUES (:u, 'garmin', :t, 'unavailable')"
            ),
            {"u": lisbon, "t": now - timedelta(minutes=20)},
        )
    assert await due(now) == {lisbon: ["yazio"]}
    assert lisbon in await due(now + timedelta(hours=1))


async def test_auth_failure_waits_for_tomorrow(env) -> None:  # type: ignore[no-untyped-def]
    admin, rw, _ = env
    user = await seed_user(admin, "Europe/Lisbon")
    await plaintext(admin, user, "garmin", {"email": "x", "password": "y"})
    now = datetime(2026, 10, 13, 9, 30, tzinfo=UTC)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO integration_sync_state (user_id, service, last_attempt_at, last_error) VALUES (:u, 'garmin', :t, 'auth_failed')"
            ),
            {"u": user, "t": now - timedelta(hours=2)},
        )
    async with rw.connect() as conn:
        today = (
            await conn.execute(
                text("SELECT count(*) FROM integration_users_due(:n, 9)"), {"n": now}
            )
        ).scalar_one()
        tomorrow = (
            await conn.execute(
                text("SELECT count(*) FROM integration_users_due(:n, 9)"),
                {"n": now + timedelta(days=1)},
            )
        ).scalar_one()
    assert (today, tomorrow) == (0, 1)


async def test_plaintext_function_lists_rows_to_reseal(env) -> None:  # type: ignore[no-untyped-def]
    admin, rw, _ = env
    a, _b = await seed_user(admin), await seed_user(admin)
    await plaintext(admin, a, "google_calendar", {"url": "x", "token": "y"})
    async with rw.connect() as conn:
        rows = (
            await conn.execute(text("SELECT user_id, service FROM credentials_plaintext()"))
        ).all()
    assert [(r.user_id, r.service) for r in rows] == [(a, "google_calendar")]


async def test_sync_state_is_tenant_isolated(env) -> None:  # type: ignore[no-untyped-def]
    admin, rw, _ = env
    a, b = await seed_user(admin), await seed_user(admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO integration_sync_state (user_id, service) VALUES (:u, 'garmin')"),
            {"u": a},
        )
    async with rw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(b)})
        assert (
            await conn.execute(text("SELECT count(*) FROM integration_sync_state"))
        ).scalar_one() == 0
    with pytest.raises(DBAPIError):  # noqa: PT012 - transaction rollback must be inside raises
        async with rw.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(b)})
            await conn.execute(
                text("INSERT INTO integration_sync_state (user_id, service) VALUES (:u, 'yazio')"),
                {"u": a},
            )


async def test_downgrade_removes_sealed_rows(clean_db: PostgresUrls) -> None:
    import asyncio

    from alembic import command
    from shared.schema.migrate import alembic_config, upgrade

    admin = create_async_engine(clean_db.admin)
    try:
        user = await seed_user(admin)
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO integrations_credentials (user_id, service, payload_enc) VALUES (:u, 'garmin', :p)"
                ),
                {"u": user, "p": b"sealed"},
            )
        try:
            await asyncio.to_thread(
                command.downgrade, alembic_config(clean_db.owner), "c0004_notifications"
            )
            async with admin.connect() as conn:
                assert (
                    await conn.execute(text("SELECT count(*) FROM integrations_credentials"))
                ).scalar_one() == 0
        finally:
            await asyncio.to_thread(upgrade, clean_db.owner)
    finally:
        await admin.dispose()


async def test_due_users_resolve_invalid_timezone_to_utc(env) -> None:  # type: ignore[no-untyped-def]
    admin, rw, _ = env
    invalid = await seed_user(admin, "Not/AZone")
    valid = await seed_user(admin, "Europe/Lisbon")
    for user in (invalid, valid):
        await plaintext(admin, user, "garmin", {"marker": "test"})
    now = datetime(2026, 10, 13, 9, 30, tzinfo=UTC)
    async with rw.connect() as conn:
        rows = (
            await conn.execute(text("SELECT * FROM integration_users_due(:n, 9)"), {"n": now})
        ).all()
    assert {r.user_id: (list(r.services), r.timezone) for r in rows} == {
        invalid: (["garmin"], "UTC"),
        valid: (["garmin"], "Europe/Lisbon"),
    }
