"""One connection per chat run: the task's advisory lock, the tenant setting and that run's saver."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any, cast

from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver
from langgraph.checkpoint.postgres.base import BasePostgresSaver
from psycopg import AsyncConnection
from psycopg_pool import AsyncConnectionPool
from shared.schema.tables import CHECKPOINT_SCHEMA_VERSION

from orchestrator.application.ports import RunContext, TaskBusy


class CheckpointSchemaMismatch(RuntimeError):
    pass


def psycopg_dsn(dsn: str) -> str:
    return dsn.replace("postgresql+asyncpg://", "postgresql://", 1)


async def _clean(conn: AsyncConnection) -> None:
    await conn.execute("SELECT pg_advisory_unlock_all()")
    await conn.execute("RESET ALL")


async def _check(conn: AsyncConnection) -> None:
    row = await (await conn.execute("SELECT current_setting('app.user_id', true)")).fetchone()
    if row and row[0]:
        raise RuntimeError("checkpoint_dirty_connection")  # the pool discards it


async def _release(conn: AsyncConnection) -> None:
    async def clean_or_close() -> None:
        try:
            await _clean(conn)
        except BaseException:
            # A connection whose reset failed must never return to another tenant.
            await conn.close()
            raise

    cleanup = asyncio.create_task(clean_or_close())
    cancelled = False
    while not cleanup.done():
        try:
            await asyncio.shield(cleanup)
        except asyncio.CancelledError:
            cancelled = True
    cleanup.result()
    if cancelled:
        raise asyncio.CancelledError


class CheckpointPool:
    def __init__(self, dsn: str, *, max_size: int) -> None:
        self._pool = AsyncConnectionPool(
            psycopg_dsn(dsn),
            min_size=0,
            max_size=max_size,
            open=False,
            kwargs={"autocommit": True, "prepare_threshold": 0},
            check=_check,
            reset=_clean,
        )

    async def open(self) -> None:
        await self._pool.open()

    async def close(self) -> None:
        await self._pool.close()

    async def verify_schema(self) -> None:
        expected = len(BasePostgresSaver.MIGRATIONS) - 1
        async with self._pool.connection() as conn:
            row = await (await conn.execute("SELECT max(v) FROM checkpoint_migrations")).fetchone()
        found = row[0] if row else None
        if expected != CHECKPOINT_SCHEMA_VERSION or found != expected:
            raise CheckpointSchemaMismatch("checkpoint_schema_mismatch")

    @asynccontextmanager
    async def session(self, ctx: RunContext) -> AsyncIterator[AsyncPostgresSaver]:
        async with self._pool.connection() as conn:
            try:
                row = await (
                    await conn.execute("SELECT pg_try_advisory_lock(hashtext(%s))", (ctx.key,))
                ).fetchone()
                if not (row and row[0]):
                    raise TaskBusy
                await conn.execute(
                    "SELECT set_config('app.user_id', %s, false)", (str(ctx.user_id),)
                )
                # The saver opens its own dict_row cursors regardless of the connection default.
                yield AsyncPostgresSaver(cast(AsyncConnection[dict[str, Any]], conn))
            finally:
                await _release(conn)
