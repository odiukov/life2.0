from uuid import UUID, uuid4

import pytest
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration

INSERT_LOG = text(
    "INSERT INTO health_logs (user_id, agent, type, data, source) "
    "VALUES (:uid, 'nutrition', 'meal', '{}'::jsonb, 'chat')"
)


async def _seed(admin: AsyncEngine) -> tuple[UUID, UUID]:
    a, b = uuid4(), uuid4()
    async with admin.begin() as conn:
        for uid in (a, b):
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:id, 'u')"), {"id": uid})
            await conn.execute(INSERT_LOG, {"uid": uid})
    return a, b


async def _count_as(engine: AsyncEngine, user: UUID | None) -> int:
    async with engine.begin() as conn:
        if user is not None:
            await conn.execute(
                text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user)}
            )
        return int((await conn.execute(text("SELECT count(*) FROM health_logs"))).scalar_one())


@pytest.fixture
async def engines(clean_db: PostgresUrls):
    admin = create_async_engine(clean_db.admin)
    rw = create_async_engine(clean_db.rw, pool_size=1, max_overflow=0)
    legacy = create_async_engine(clean_db.legacy)
    yield admin, rw, legacy
    for engine in (admin, rw, legacy):
        await engine.dispose()


async def test_tenant_sees_only_own_rows(engines) -> None:
    admin, rw, _ = engines
    a, _b = await _seed(admin)
    assert await _count_as(rw, a) == 1


async def test_no_tenant_sees_nothing_even_after_reuse_of_a_tenant_connection(engines) -> None:
    admin, rw, _ = engines
    a, _ = await _seed(admin)
    assert await _count_as(rw, a) == 1  # same pooled connection is reused below
    assert await _count_as(rw, None) == 0


async def test_tenant_cannot_write_for_someone_else(engines) -> None:
    admin, rw, _ = engines
    a, b = await _seed(admin)
    with pytest.raises(DBAPIError, match="row-level security"):
        await _insert_as(rw, str(a), INSERT_LOG, {"uid": b})


async def test_tenant_reads_own_user_row_only(engines) -> None:
    admin, rw, _ = engines
    a, _ = await _seed(admin)
    async with rw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(a)})
        ids = (await conn.execute(text("SELECT id FROM users"))).scalars().all()
    assert ids == [a]


async def test_legacy_role_bypasses_rls(engines) -> None:
    admin, _, legacy = engines
    await _seed(admin)
    assert await _count_as(legacy, None) == 2


async def test_rw_reads_tables_without_rls(engines) -> None:
    _, rw, _ = engines
    async with rw.begin() as conn:
        assert (await conn.execute(text("SELECT count(*) FROM tasks"))).scalar_one() == 0


@pytest.mark.parametrize("identity", [None, "a", "b"])
async def test_consent_reads_are_tenant_scoped(engines, identity):
    admin, rw, _ = engines
    a, b = await _seed(admin)
    user = {"a": a, "b": b, None: None}[identity]
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES (:a,true),(:b,false)"),
            {"a": a, "b": b},
        )
    async with rw.begin() as conn:
        if user is not None:
            await conn.execute(
                text("SELECT set_config('app.user_id', :uid, true)"), {"uid": str(user)}
            )
        ids = (await conn.execute(text("SELECT user_id FROM telemetry_consent"))).scalars().all()
    assert ids == ([] if user is None else [user])


@pytest.mark.parametrize("has_tenant", [False, True])
async def test_consent_cannot_insert_another_tenants_row(engines, has_tenant):
    admin, rw, _ = engines
    a, b = await _seed(admin)
    with pytest.raises(DBAPIError, match="row-level security"):
        await _insert_as(
            rw,
            str(a) if has_tenant else None,
            text("INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES (:b, true)"),
            {"b": b},
        )


async def test_consent_cannot_update_another_tenants_row(engines):
    admin, rw, _ = engines
    a, b = await _seed(admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO telemetry_consent (user_id, bodies_ok) VALUES (:a,false),(:b,false)"),
            {"a": a, "b": b},
        )
    async with rw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :a, true)"), {"a": str(a)})
        result = await conn.execute(
            text("UPDATE telemetry_consent SET bodies_ok = true WHERE user_id = :b"), {"b": b}
        )
        assert result.rowcount == 0
        await conn.execute(
            text("UPDATE telemetry_consent SET bodies_ok = true WHERE user_id = :a"), {"a": a}
        )
    async with admin.connect() as conn:
        rows = (await conn.execute(text("SELECT user_id, bodies_ok FROM telemetry_consent"))).all()
    assert set(rows) == {(a, True), (b, False)}
    async with rw.begin() as conn:
        assert (
            await conn.execute(text("SELECT count(*) FROM telemetry_consent"))
        ).scalar_one() == 0


async def test_all_tenant_tables_enable_and_force_rls(postgres_urls):
    from shared.schema.tables import RLS_TABLES

    engine = create_async_engine(postgres_urls.admin)
    try:
        async with engine.connect() as conn:
            rows = (
                await conn.execute(
                    text(
                        "SELECT relname, relrowsecurity, relforcerowsecurity FROM pg_class JOIN pg_namespace ON pg_namespace.oid = pg_class.relnamespace WHERE nspname = 'public' AND relkind = 'r'"
                    )
                )
            ).all()
        actual = {name: (enabled, forced) for name, enabled, forced in rows}
        assert {name: actual[name] for name in (*RLS_TABLES, "users")} == dict.fromkeys(
            (*RLS_TABLES, "users"), (True, True)
        )
    finally:
        await engine.dispose()


async def test_table_owner_is_also_subject_to_rls(clean_db):
    admin = create_async_engine(clean_db.admin)
    owner = create_async_engine(clean_db.owner)
    try:
        await _seed(admin)
        assert await _count_as(owner, None) == 0
    finally:
        await admin.dispose()
        await owner.dispose()


async def _insert_as(engine, user, statement, values):
    async with engine.begin() as conn:
        if user is not None:
            await conn.execute(text("SELECT set_config('app.user_id', :uid, true)"), {"uid": user})
        await conn.execute(statement, values)
