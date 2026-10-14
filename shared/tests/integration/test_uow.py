import asyncio
from contextlib import nullcontext
from uuid import UUID, uuid4

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.config import DatabaseSettings
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import bindparam, event, text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncConnection, create_async_engine

pytestmark = pytest.mark.integration


class Users:
    def __init__(self, conn: AsyncConnection) -> None:
        self.conn = conn

    async def names(self) -> list[str]:
        rows = await self.conn.execute(text("SELECT name FROM users ORDER BY name"))
        return list(rows.scalars())

    async def rename(self, user_id: UUID, name: str) -> None:
        await self.conn.execute(
            text("UPDATE users SET name = :name WHERE id = :id"), {"name": name, "id": user_id}
        )


class Unregistered:
    pass


@pytest.fixture
async def setup(clean_db: PostgresUrls):
    admin = create_async_engine(clean_db.admin)
    a, b = uuid4(), uuid4()
    try:
        async with admin.begin() as conn:
            await conn.execute(
                text("INSERT INTO users (id, name) VALUES (:a, 'alice'), (:b, 'bob')"),
                {"a": a, "b": b},
            )
    finally:
        await admin.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw, "pool_size": 1}))
    try:
        yield SqlUnitOfWorkFactory(engine, {Users: Users}), a, b, engine
    finally:
        await engine.dispose()


async def test_for_user_sees_only_the_tenant(setup) -> None:
    factory, a, _, _ = setup
    async with factory.for_user(a) as uow:
        repo = uow.repo(Users)
        assert repo is uow.repo(Users)
        assert await repo.names() == ["alice"]


async def test_clean_exit_commits(setup) -> None:
    factory, a, _, _ = setup
    async with factory.for_user(a) as uow:
        await uow.repo(Users).rename(a, "alicia")
    async with factory.for_user(a) as uow:
        assert await uow.repo(Users).names() == ["alicia"]


async def test_exception_rolls_back(setup) -> None:
    factory, a, _, _ = setup
    with pytest.raises(RuntimeError):  # noqa: PT012 - exercise the transaction body and its exit
        async with factory.for_user(a) as uow:
            await uow.repo(Users).rename(a, "lost")
            raise RuntimeError("boom")
    async with factory.for_user(a) as uow:
        assert await uow.repo(Users).names() == ["alice"]


async def test_system_scope_sees_no_tenant_rows(setup) -> None:
    factory, _, _, _ = setup
    async with factory.system() as uow:
        assert await uow.repo(Users).names() == []
        count = (await uow.connection.execute(text("SELECT count(*) FROM tasks"))).scalar_one()
        assert count == 0


async def test_unknown_repository_is_a_lookup_error(setup) -> None:
    factory, a, _, _ = setup
    async with factory.for_user(a) as uow:
        with pytest.raises(LookupError, match="Unregistered"):
            uow.repo(Unregistered)
        assert await uow.repo(Users).names() == ["alice"]


@pytest.mark.parametrize("abort", [False, True])
async def test_tenant_is_reset_when_the_same_pooled_connection_is_reused(setup, abort) -> None:
    factory, a, b, _ = setup
    first = factory.for_user(a)
    with pytest.raises(RuntimeError) if abort else nullcontext():
        async with first as uow:
            pid = (await uow.connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
            assert await uow.repo(Users).names() == ["alice"]
            if abort:
                raise RuntimeError("abort")
    async with factory.system() as uow:
        assert (await uow.connection.execute(text("SELECT pg_backend_pid()"))).scalar_one() == pid
        assert await uow.repo(Users).names() == []
        assert (
            await uow.connection.execute(
                text("SELECT NULLIF(current_setting('app.user_id', true), '')")
            )
        ).scalar_one() is None
    async with factory.for_user(b) as uow:
        assert (await uow.connection.execute(text("SELECT pg_backend_pid()"))).scalar_one() == pid
        assert await uow.repo(Users).names() == ["bob"]


async def test_repositories_are_bound_to_one_transaction(setup) -> None:
    factory, a, _, _ = setup
    scope = factory.for_user(a)
    async with scope as uow:
        first = uow.repo(Users)
        assert first.conn is uow.connection
    assert first.conn.closed
    async with scope as uow:
        second = uow.repo(Users)
        assert second is not first
        assert second.conn is uow.connection
        assert await second.names() == ["alice"]


async def test_connection_and_repository_require_an_active_scope(setup) -> None:
    factory, a, _, _ = setup
    scope = factory.for_user(a)
    with pytest.raises(RuntimeError, match="outside"):
        _ = scope.connection
    with pytest.raises(RuntimeError, match="outside"):
        scope.repo(Users)
    async with scope as uow:
        uow.repo(Users)
    with pytest.raises(RuntimeError, match="outside"):
        _ = scope.connection
    with pytest.raises(RuntimeError, match="outside"):
        scope.repo(Users)


@pytest.mark.parametrize("operation", ["begin", "tenant"])
async def test_failed_entry_returns_the_connection_to_the_pool(setup, operation) -> None:
    factory, a, _, engine = setup

    def fail(*args):
        raise RuntimeError("entry failed")

    event_name = "begin" if operation == "begin" else "before_cursor_execute"
    event.listen(engine.sync_engine, event_name, fail)
    scope = factory.for_user(a)
    try:
        with pytest.raises(RuntimeError, match="entry failed"):
            async with scope:
                pytest.fail("entry must fail")
    finally:
        event.remove(engine.sync_engine, event_name, fail)
    assert engine.pool.checkedout() == 0
    with pytest.raises(RuntimeError, match="outside"):
        _ = scope.connection
    async with factory.system() as uow:
        assert await uow.repo(Users).names() == []
    async with factory.for_user(a) as uow:
        assert await uow.repo(Users).names() == ["alice"]


async def test_failed_commit_closes_connection_and_discards_repositories(setup) -> None:
    factory, a, _, engine = setup

    def fail(conn):
        raise RuntimeError("commit failed")

    scope = factory.for_user(a)
    event.listen(engine.sync_engine, "commit", fail)
    try:
        with pytest.raises(RuntimeError, match="commit failed"):  # noqa: PT012
            async with scope as uow:
                previous = uow.repo(Users)
                await previous.rename(a, "lost")
    finally:
        event.remove(engine.sync_engine, "commit", fail)
    assert engine.pool.checkedout() == 0
    assert previous.conn.closed
    with pytest.raises(RuntimeError, match="outside"):
        _ = scope.connection
    async with scope as uow:
        assert uow.repo(Users) is not previous
        assert await uow.repo(Users).names() == ["alice"]


async def test_engine_serializes_unicode_and_uuid_json(setup) -> None:
    factory, a, _, _ = setup
    statement = text("SELECT :payload").bindparams(bindparam("payload", type_=JSONB))
    async with factory.for_user(a) as uow:
        value = (
            await uow.connection.execute(statement, {"payload": {"name": "café", "id": a}})
        ).scalar_one()
        assert value == {"name": "café", "id": str(a)}


async def test_engine_reconnects_after_an_idle_connection_is_terminated(setup, clean_db) -> None:
    factory, a, _, _ = setup
    async with factory.for_user(a) as uow:
        pid = (await uow.connection.execute(text("SELECT pg_backend_pid()"))).scalar_one()
    admin = create_async_engine(clean_db.admin)
    try:
        async with admin.connect() as conn:
            assert (
                await conn.execute(text("SELECT pg_terminate_backend(:pid)"), {"pid": pid})
            ).scalar_one()
        async with factory.for_user(a) as uow:
            assert (
                await uow.connection.execute(text("SELECT pg_backend_pid()"))
            ).scalar_one() != pid
            assert await uow.repo(Users).names() == ["alice"]
    finally:
        await admin.dispose()


async def test_nested_entry_is_rejected_without_replacing_the_active_transaction(setup) -> None:
    factory, a, _, engine = setup
    scope = factory.for_user(a)
    original = None
    try:
        async with scope as uow:
            original = uow.connection
            repo = uow.repo(Users)
            with pytest.raises(RuntimeError, match="already"):
                await scope.__aenter__()
            assert uow.connection is original
            assert uow.repo(Users) is repo
            assert engine.pool.checkedout() == 1
            await repo.rename(a, "alicia")
    finally:
        if original is not None:
            await original.close()
    assert engine.pool.checkedout() == 0
    async with scope as uow:
        assert uow.repo(Users) is not repo
        assert await uow.repo(Users).names() == ["alicia"]


async def test_concurrent_entry_is_rejected_while_first_checkout_is_in_progress(setup) -> None:
    factory, a, _, engine = setup
    scope = factory.for_user(a)
    started, release = asyncio.Event(), asyncio.Event()
    extra = []

    async def wait_for_release(driver):
        started.set()
        await release.wait()

    def pause_first_checkout(dbapi, record):
        if not started.is_set():
            dbapi.run_async(wait_for_release)

    async def enter_again():
        await scope.__aenter__()
        extra.append(scope.connection)

    event.listen(engine.sync_engine, "connect", pause_first_checkout)
    first = asyncio.create_task(scope.__aenter__())
    try:
        await asyncio.wait_for(started.wait(), timeout=5)
        with pytest.raises(RuntimeError, match="already"):
            await asyncio.wait_for(enter_again(), timeout=2)
    finally:
        release.set()
        await first
        event.remove(engine.sync_engine, "connect", pause_first_checkout)
        await scope.__aexit__(None, None, None)
        for connection in extra:
            await connection.close()
    assert engine.pool.checkedout() == 0
    async with scope as uow:
        assert await uow.repo(Users).names() == ["alice"]


@pytest.mark.parametrize("secondary", ["invalidate", "close", "both"])
@pytest.mark.parametrize("primary_kind", ["error", "cancellation"])
async def test_cleanup_failure_preserves_commit_error_and_discards_driver(
    setup, monkeypatch, secondary, primary_kind
) -> None:
    factory, a, _, engine = setup
    scope = factory.for_user(a)
    error_type = RuntimeError if primary_kind == "error" else asyncio.CancelledError
    primary = error_type("primary commit failure")
    original_close = AsyncConnection.close
    close_failed = False

    def fail_commit(conn):
        raise primary

    def fail_invalidation(dbapi, record, error):
        raise ValueError("secondary invalidation failure")

    async def fail_close_once(conn):
        nonlocal close_failed
        if conn is connection and not close_failed:
            close_failed = True
            raise ValueError("secondary close failure")
        await original_close(conn)

    event.listen(engine.sync_engine, "commit", fail_commit)
    if secondary in ("invalidate", "both"):
        event.listen(engine.sync_engine, "invalidate", fail_invalidation)
    if secondary in ("close", "both"):
        monkeypatch.setattr(AsyncConnection, "close", fail_close_once)
    try:
        with pytest.raises(error_type, match="primary commit failure") as caught:  # noqa: PT012
            async with scope as uow:
                previous = uow.repo(Users)
                connection = uow.connection
                driver = (await connection.get_raw_connection()).driver_connection
                await previous.rename(a, "lost")
        driver_closed, checked_out = driver.is_closed(), engine.pool.checkedout()
    finally:
        event.remove(engine.sync_engine, "commit", fail_commit)
        if secondary in ("invalidate", "both"):
            event.remove(engine.sync_engine, "invalidate", fail_invalidation)
        monkeypatch.setattr(AsyncConnection, "close", original_close)
        if not connection.closed:
            await connection.invalidate()
        await connection.close()
    assert caught.value is primary
    notes = " ".join(primary.__notes__)
    if secondary in ("invalidate", "both"):
        assert "secondary invalidation failure" in notes
    if secondary in ("close", "both"):
        assert "secondary close failure" in notes
    assert driver_closed
    assert checked_out == 0
    with pytest.raises(RuntimeError, match="outside"):
        _ = scope.connection
    async with scope as uow:
        assert uow.repo(Users) is not previous
        assert await uow.repo(Users).names() == ["alice"]


async def test_close_failure_after_successful_commit_is_surfaced_and_scope_can_be_reused(
    setup, monkeypatch
) -> None:
    factory, a, _, engine = setup
    scope = factory.for_user(a)
    close_error = ValueError("close failed after commit")
    original_close = AsyncConnection.close
    close_failed = False

    async def fail_close_once(conn):
        nonlocal close_failed
        if conn is connection and not close_failed:
            close_failed = True
            raise close_error
        await original_close(conn)

    monkeypatch.setattr(AsyncConnection, "close", fail_close_once)
    try:
        with pytest.raises(ValueError, match="close failed after commit") as caught:  # noqa: PT012
            async with scope as uow:
                previous = uow.repo(Users)
                connection = uow.connection
                driver = (await connection.get_raw_connection()).driver_connection
                await previous.rename(a, "alicia")
        driver_closed, checked_out = driver.is_closed(), engine.pool.checkedout()
    finally:
        monkeypatch.setattr(AsyncConnection, "close", original_close)
        await connection.close()
    assert caught.value is close_error
    assert driver_closed
    assert checked_out == 0
    with pytest.raises(RuntimeError, match="outside"):
        _ = scope.connection
    async with scope as uow:
        assert uow.repo(Users) is not previous
        assert await uow.repo(Users).names() == ["alicia"]


async def test_entry_failure_preserves_primary_error_when_close_fails(setup, monkeypatch) -> None:
    factory, a, _, engine = setup
    scope = factory.for_user(a)
    primary = RuntimeError("primary tenant initialization failure")
    original_close = AsyncConnection.close
    close_failed = False
    connections = []

    def fail_entry(conn, *args):
        raise primary

    async def fail_close_once(conn):
        nonlocal close_failed
        connections.append(conn)
        if not close_failed:
            close_failed = True
            raise ValueError("secondary entry close failure")
        await original_close(conn)

    event.listen(engine.sync_engine, "before_cursor_execute", fail_entry)
    monkeypatch.setattr(AsyncConnection, "close", fail_close_once)
    try:
        with pytest.raises(RuntimeError, match="primary tenant initialization failure") as caught:
            await scope.__aenter__()
        checked_out = engine.pool.checkedout()
    finally:
        event.remove(engine.sync_engine, "before_cursor_execute", fail_entry)
        monkeypatch.setattr(AsyncConnection, "close", original_close)
        for connection in connections:
            if not connection.closed:
                await connection.invalidate()
            await connection.close()
    assert caught.value is primary
    assert "secondary entry close failure" in " ".join(primary.__notes__)
    assert checked_out == 0
    with pytest.raises(RuntimeError, match="outside"):
        _ = scope.connection
    async with scope as uow:
        assert await uow.repo(Users).names() == ["alice"]
