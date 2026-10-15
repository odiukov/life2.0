import pytest
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
from alembic.script import ScriptDirectory
from shared.schema import metadata
from shared.schema.migrate import alembic_config, downgrade, upgrade
from shared.testing.pytest_plugin import PostgresUrls, run_blocking
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


async def _diff(url: str) -> list[object]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return await conn.run_sync(
                lambda sync: compare_metadata(MigrationContext.configure(sync), metadata)
            )
    finally:
        await engine.dispose()


async def test_database_matches_metadata(postgres_urls: PostgresUrls) -> None:
    assert await _diff(postgres_urls.owner) == []


def test_downgrade_and_upgrade_round_trip(postgres_urls: PostgresUrls) -> None:
    downgrade(postgres_urls.owner)
    upgrade(postgres_urls.owner)
    assert run_blocking(_diff(postgres_urls.owner)) == []


async def test_telemetry_consent_uses_uuid_without_seed(postgres_urls: PostgresUrls) -> None:
    engine = create_async_engine(postgres_urls.admin)
    try:
        async with engine.connect() as conn:
            assert (
                await conn.execute(text("SELECT count(*) FROM telemetry_consent"))
            ).scalar_one() == 0
            assert (
                await conn.execute(
                    text(
                        "SELECT data_type FROM information_schema.columns WHERE table_name = 'telemetry_consent' AND column_name = 'user_id'"
                    )
                )
            ).scalar_one() == "uuid"
    finally:
        await engine.dispose()


async def test_role_bootstrap_is_idempotent_and_restores_separation(postgres_urls):
    from shared.schema.migrate import ensure_roles
    from shared.testing.pytest_plugin import TEST_PASSWORDS

    engine = create_async_engine(postgres_urls.admin)
    try:
        async with engine.begin() as conn:
            await conn.execute(
                text("ALTER ROLE app_rw SUPERUSER CREATEDB CREATEROLE REPLICATION BYPASSRLS")
            )
            await conn.execute(text("GRANT CREATE ON SCHEMA public TO PUBLIC, app_rw"))
        for _ in range(2):
            await ensure_roles(postgres_urls.admin, postgres_urls.database, TEST_PASSWORDS)
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT rolname, rolsuper, rolcreatedb, rolcreaterole, rolreplication, rolbypassrls FROM pg_roles WHERE rolname IN ('app_owner', 'app_rw', 'app_legacy') ORDER BY rolname"
                    )
                )
            ).all()
            assert rows == [
                ("app_legacy", False, False, False, False, True),
                ("app_owner", False, False, False, False, False),
                ("app_rw", False, False, False, False, False),
            ]
            assert (
                await conn.execute(
                    text(
                        "SELECT has_schema_privilege('app_owner', 'public', 'CREATE'), has_schema_privilege('app_rw', 'public', 'CREATE'), has_schema_privilege('app_legacy', 'public', 'CREATE')"
                    )
                )
            ).one() == (True, False, True)
            assert (
                await conn.execute(
                    text(
                        "SELECT tableowner FROM pg_tables WHERE schemaname = 'public' AND tablename = 'health_logs'"
                    )
                )
            ).scalar_one() == "app_owner"
    finally:
        await engine.dispose()


async def test_rw_cannot_ddl_and_legacy_can_create_checkpoint_tables(postgres_urls):
    import pytest
    from sqlalchemy.exc import DBAPIError

    rw = create_async_engine(postgres_urls.rw)
    legacy = create_async_engine(postgres_urls.legacy)
    owner = create_async_engine(postgres_urls.owner)
    try:
        with pytest.raises(DBAPIError, match="permission denied"):
            async with rw.begin() as conn:
                await conn.execute(text("CREATE TABLE forbidden (id integer)"))
        with pytest.raises(DBAPIError, match="must be owner"):
            async with rw.begin() as conn:
                await conn.execute(text("ALTER TABLE tasks ADD COLUMN forbidden integer"))
        async with legacy.begin() as conn:
            await conn.execute(text("CREATE TABLE checkpoint_probe (id integer)"))
            await conn.execute(text("DROP TABLE checkpoint_probe"))
        async with owner.begin() as conn:
            await conn.execute(text("CREATE TABLE owner_probe (id integer)"))
            await conn.execute(text("DROP TABLE owner_probe"))
    finally:
        for engine in (rw, legacy, owner):
            await engine.dispose()


@pytest.mark.parametrize("role", ["app_rw", "app_legacy"])
async def test_application_roles_cannot_access_migration_control_table(postgres_urls, role):
    from shared.schema.migrate import ensure_roles
    from shared.testing.pytest_plugin import TEST_PASSWORDS
    from sqlalchemy.exc import DBAPIError

    # Bootstrapping roles again must preserve migration-control separation.
    for _ in range(2):
        await ensure_roles(postgres_urls.admin, postgres_urls.database, TEST_PASSWORDS)
    owner = create_async_engine(postgres_urls.owner)
    application = create_async_engine(
        postgres_urls.rw if role == "app_rw" else postgres_urls.legacy
    )
    try:
        async with owner.connect() as conn:
            assert (
                await conn.execute(text("SELECT version_num FROM alembic_version"))
            ).scalar_one() == ScriptDirectory.from_config(
                alembic_config(postgres_urls.owner)
            ).get_current_head()
            allowed = (
                await conn.execute(
                    text(
                        "SELECT has_table_privilege(:role, 'alembic_version', 'SELECT,INSERT,UPDATE,DELETE,TRUNCATE,REFERENCES,TRIGGER')"
                    ),
                    {"role": role},
                )
            ).scalar_one()
        assert allowed is False
        async with application.begin() as conn:
            with pytest.raises(DBAPIError, match="permission denied for table alembic_version"):
                await conn.execute(text("UPDATE alembic_version SET version_num = version_num"))
        # The non-tenant application task table keeps its system DML grant.
        async with application.begin() as conn:
            await conn.execute(text("INSERT INTO tasks (agent) VALUES ('privilege-probe')"))
            assert (
                await conn.execute(
                    text("SELECT count(*) FROM tasks WHERE agent = 'privilege-probe'")
                )
            ).scalar_one() == 1
            await conn.execute(text("DELETE FROM tasks WHERE agent = 'privilege-probe'"))
    finally:
        await owner.dispose()
        await application.dispose()


async def test_chat_upgrade_preserves_valid_consent_and_legacy_checkpoint_access(postgres_urls):
    from uuid import UUID, uuid4

    from alembic import command
    from shared.schema.migrate import ensure_roles
    from shared.testing.pytest_plugin import TEST_PASSWORDS

    admin = create_async_engine(postgres_urls.admin)
    legacy = create_async_engine(postgres_urls.legacy)
    user = UUID("aabbccdd-1111-4222-8333-123456789abc")
    other = uuid4()

    def run_blocking_target():
        return command.downgrade(alembic_config(postgres_urls.owner), "c0009_auth_functions")

    # Alembic runs its own event loop.
    import asyncio

    await asyncio.to_thread(run_blocking_target)
    try:
        async with admin.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id,name) VALUES (:u,'a'),(:o,'b')"),
                {"u": user, "o": other},
            )
            await conn.execute(
                text(
                    "INSERT INTO telemetry_consent (user_id,bodies_ok) VALUES (:u,true),(:upper,false),(:o,true),(:orphan,true),('bad-input',true)"
                ),
                {
                    "u": str(user),
                    "upper": str(user).upper(),
                    "o": str(other),
                    "orphan": str(uuid4()),
                },
            )
        async with legacy.begin() as conn:
            await conn.execute(text("CREATE TABLE checkpoints (thread_id text)"))
            await conn.execute(text("INSERT INTO checkpoints VALUES ('old-unowned-thread')"))
        await ensure_roles(postgres_urls.admin, postgres_urls.database, TEST_PASSWORDS)
        await asyncio.to_thread(upgrade, postgres_urls.owner)
        async with admin.connect() as conn:
            rows = (
                await conn.execute(text("SELECT user_id,bodies_ok FROM telemetry_consent"))
            ).all()
            assert set(rows) == {(user, False), (other, True)}
            assert (await conn.execute(text("SELECT count(*) FROM checkpoints"))).scalar_one() == 0
            assert (
                await conn.execute(
                    text("SELECT relforcerowsecurity FROM pg_class WHERE oid = 'users'::regclass")
                )
            ).scalar_one() is True
        # Task 13 still runs the old orchestrator as app_legacy.
        async with legacy.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO checkpoints (thread_id, checkpoint_id, checkpoint) VALUES ('legacy-thread', 'c1', '{}')"
                )
            )
            assert (
                await conn.execute(text("SELECT max(v) FROM checkpoint_migrations"))
            ).scalar_one() == 9
    finally:
        await asyncio.to_thread(upgrade, postgres_urls.owner)
        await admin.dispose()
        await legacy.dispose()
