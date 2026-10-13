from __future__ import annotations

from types import TracebackType
from typing import Protocol, Self, TypeVar
from uuid import UUID

RepoT = TypeVar("RepoT")


class UnitOfWork(Protocol):
    """One database transaction. Commits on a clean exit, rolls back on an exception."""

    async def __aenter__(self) -> Self: ...

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None: ...

    def repo(self, kind: type[RepoT]) -> RepoT:
        """Repository registered for this protocol type, bound to this transaction."""
        ...


class UnitOfWorkFactory(Protocol):
    def for_user(self, user_id: UUID) -> UnitOfWork:
        """Transaction scoped to one tenant (row-level security applies)."""
        ...

    def system(self) -> UnitOfWork:
        """Transaction without a tenant; only tables without RLS are visible."""
        ...
