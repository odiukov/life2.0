"""Unit of Work: one connection + transaction; tenant set with a transaction-local GUC."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from types import TracebackType
from typing import Any, Self, TypeVar, cast
from uuid import UUID

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

RepoT = TypeVar("RepoT")
RepoFactory = Callable[[AsyncConnection], Any]

_SET_TENANT = text("SELECT set_config('app.user_id', :uid, true)")


class SqlUnitOfWork:
    def __init__(
        self, engine: AsyncEngine, factories: Mapping[type[Any], RepoFactory], user_id: UUID | None
    ) -> None:
        self._engine = engine
        self._factories = factories
        self._user_id = user_id
        self._conn: AsyncConnection | None = None
        self._repos: dict[type[Any], Any] = {}
        self._active = False

    async def __aenter__(self) -> Self:
        if self._active:
            raise RuntimeError("UnitOfWork is already active or entering")
        self._active = True
        conn: AsyncConnection | None = None
        try:
            conn = await self._engine.connect()
            await conn.begin()
            if self._user_id is not None:
                await conn.execute(_SET_TENANT, {"uid": str(self._user_id)})
        except BaseException as error:
            try:
                if conn is not None:
                    await self._cleanup(conn, error)
            finally:
                self._reset()
            raise
        self._conn = conn
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        conn = self.connection
        error: BaseException | None = None
        try:
            try:
                if exc_type is None:
                    await conn.commit()
                else:
                    await conn.rollback()
            except BaseException as finalization_error:
                error = finalization_error
            error = await self._cleanup(conn, error)
        finally:
            self._reset()
        if error is not None:
            raise error

    def _reset(self) -> None:
        self._conn = None
        self._repos.clear()
        self._active = False

    async def _cleanup(
        self, conn: AsyncConnection, error: BaseException | None
    ) -> BaseException | None:
        if error is not None:
            await self._discard(conn, error)
        try:
            await conn.close()
        except BaseException as close_error:
            if error is None:
                error = close_error
            else:
                error.add_note(f"Connection close failed: {close_error!r}")
            await self._discard(conn, error)
            try:
                await conn.close()
            except BaseException as retry_error:
                error.add_note(f"Connection close retry failed: {retry_error!r}")
        return error

    async def _discard(self, conn: AsyncConnection, error: BaseException) -> None:
        if conn.invalidated or conn.closed:
            return
        raw = None
        try:
            raw = await conn.get_raw_connection()
        except BaseException as driver_error:
            error.add_note(f"Driver access failed during cleanup: {driver_error!r}")
        try:
            # Failed finalization may leave a driver transaction open after SQLAlchemy
            # marks it inactive. Never return that driver as a usable pooled connection.
            await conn.invalidate()
        except BaseException as invalidate_error:
            error.add_note(f"Connection invalidation failed: {invalidate_error!r}")
            if raw is not None:
                try:
                    raw.detach()
                except BaseException as detach_error:
                    error.add_note(f"Connection detach failed: {detach_error!r}")
                try:
                    # The asyncpg adapter terminates synchronously outside a greenlet,
                    # bypassing pool listeners and clearing its driver transaction state.
                    if raw.dbapi_connection is not None:
                        raw.dbapi_connection.terminate()
                except BaseException as terminate_error:
                    error.add_note(f"Driver termination failed: {terminate_error!r}")

    @property
    def connection(self) -> AsyncConnection:
        if self._conn is None:
            raise RuntimeError("UnitOfWork used outside `async with`")
        return self._conn

    def repo(self, kind: type[RepoT]) -> RepoT:
        if kind not in self._repos:
            try:
                factory = self._factories[kind]
            except KeyError:
                raise LookupError(f"no repository registered for {kind.__name__}") from None
            self._repos[kind] = factory(self.connection)
        return cast(RepoT, self._repos[kind])


class SqlUnitOfWorkFactory:
    def __init__(self, engine: AsyncEngine, repositories: Mapping[type[Any], RepoFactory]) -> None:
        self._engine = engine
        self._repositories = dict(repositories)

    def for_user(self, user_id: UUID) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._engine, self._repositories, user_id)

    def system(self) -> SqlUnitOfWork:
        return SqlUnitOfWork(self._engine, self._repositories, None)
