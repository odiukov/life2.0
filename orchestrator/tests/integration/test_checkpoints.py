import asyncio
from datetime import UTC, datetime
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from orchestrator.adapters.langgraph.checkpoints import CheckpointPool, CheckpointSchemaMismatch
from orchestrator.application.ports import RunContext, TaskBusy
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


def ctx(user=None, task=None) -> RunContext:  # type: ignore[no-untyped-def]
    return RunContext(
        user or uuid4(), task or uuid4(), None, None, ZoneInfo("UTC"), "en", datetime.now(UTC)
    )


@pytest.fixture
async def pool(clean_db: PostgresUrls):
    pool = CheckpointPool(clean_db.rw, max_size=2)
    await pool.open()
    try:
        yield pool
    finally:
        await pool.close()


async def test_a_second_run_on_the_same_task_is_busy(pool) -> None:
    c = ctx()
    async with pool.session(c):
        with pytest.raises(TaskBusy):
            async with pool.session(c):
                pass
    async with pool.session(c):
        pass  # released


async def test_cancelled_run_releases_the_task_lock(pool) -> None:
    """Review Focus 1: the app disconnects mid-run; the next message must not be busy forever."""
    c = ctx()
    started = asyncio.Event()

    async def run() -> None:
        async with pool.session(c):
            started.set()
            await asyncio.sleep(3600)

    task = asyncio.create_task(run())
    await started.wait()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task
    async with pool.session(c):
        pass


async def test_the_tenant_setting_never_leaks_between_runs(pool, clean_db: PostgresUrls) -> None:
    a, b = ctx(), ctx()
    async with pool.session(a) as saver:
        conn = saver.conn  # the run's single connection
        assert (
            await (await conn.execute("SELECT current_setting('app.user_id', true)")).fetchone()
        )[0] == str(a.user_id)
    async with pool.session(b) as saver:
        assert (
            await (
                await saver.conn.execute("SELECT current_setting('app.user_id', true)")
            ).fetchone()
        )[0] == str(b.user_id)


async def test_schema_mismatch_stops_startup(pool, clean_db: PostgresUrls) -> None:
    await pool.verify_schema()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(text("DELETE FROM checkpoint_migrations WHERE v = 9"))
    try:
        with pytest.raises(CheckpointSchemaMismatch):
            await pool.verify_schema()
    finally:
        async with admin.begin() as conn:
            await conn.execute(text("INSERT INTO checkpoint_migrations VALUES (9)"))
        await admin.dispose()


async def test_check_rejects_a_connection_carrying_a_tenant(clean_db: PostgresUrls) -> None:
    from orchestrator.adapters.langgraph.checkpoints import _check, psycopg_dsn
    from psycopg import AsyncConnection

    conn = await AsyncConnection.connect(psycopg_dsn(clean_db.rw), autocommit=True)
    try:
        await conn.execute("SELECT set_config('app.user_id', %s, false)", (str(uuid4()),))
        with pytest.raises(RuntimeError, match="checkpoint_dirty_connection"):
            await _check(conn)
    finally:
        await conn.close()


async def test_repeated_cancellation_waits_for_cleanup_before_returning_connection(
    pool, monkeypatch
) -> None:
    import orchestrator.adapters.langgraph.checkpoints as checkpoints

    original = checkpoints._clean
    cleaning, release = asyncio.Event(), asyncio.Event()
    connections = []

    async def slow_clean(conn):
        connections.append(conn)
        cleaning.set()
        await release.wait()
        await original(conn)

    monkeypatch.setattr(checkpoints, "_clean", slow_clean)
    entered = asyncio.Event()
    c = ctx()

    async def run():
        async with pool.session(c):
            entered.set()
            await asyncio.sleep(3600)

    task = asyncio.create_task(run())
    await entered.wait()
    task.cancel()
    await cleaning.wait()
    task.cancel()
    await asyncio.sleep(0.02)
    try:
        assert not task.done()
    finally:
        release.set()
        with pytest.raises(asyncio.CancelledError):
            await task
    conn = connections[0]
    row = await (await conn.execute("SELECT current_setting('app.user_id', true)")).fetchone()
    assert not row[0]
    async with pool.session(c):
        pass
