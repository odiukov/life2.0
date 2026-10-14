"""Test helpers and in-memory repositories with the same contract as the SQL ones."""

from __future__ import annotations

import asyncio
from collections.abc import Sequence
from dataclasses import dataclass, field, replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from types import TracebackType
from typing import Any, Self, TypeVar
from uuid import UUID, uuid4

from shared.testing.fakes import InMemoryUnitOfWorkFactory

from kitchen.application.ports import (
    BatchRepository,
    ClarificationRepository,
    HouseholdContext,
    HouseholdView,
    OperationGroup,
    OperationLog,
    PendingClarification,
    UserLocales,
)
from kitchen.domain.model import Batch, Category, ExpirySource, Location, Source, Status, Unit
from kitchen.domain.rules import fifo

RepoT = TypeVar("RepoT")

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
TODAY = date(2026, 10, 13)


def make_batch(**overrides: Any) -> Batch:
    """Brownie-compatible builder: integer ids/authors become UUID(int=n); ids keep FIFO order."""
    raw_id = overrides.get("id")
    if isinstance(raw_id, int):
        overrides["id"] = UUID(int=raw_id)
        overrides.setdefault("added_at", NOW + timedelta(microseconds=raw_id))
    if isinstance(overrides.get("added_by"), int):
        overrides["added_by"] = UUID(int=overrides["added_by"])
    base = Batch(
        id=None,
        name="молоко",
        display_name="молоко 3.2%",
        category=Category.DAIRY,
        quantity=Decimal("1000"),
        unit=Unit.ML,
        location=Location.FRIDGE,
        status=Status.ACTIVE,
        opened=False,
        opened_on=None,
        added_at=NOW,
        added_by=None,
        expires_on=date(2026, 10, 20),
        expiry_source=ExpirySource.ESTIMATED,
        next_check_on=date(2026, 10, 19),
        source=Source.TEXT,
    )
    return replace(base, **overrides)


class InMemoryBatches:
    def __init__(self) -> None:
        self.rows: dict[UUID, Batch] = {}
        self.last_group: dict[UUID, UUID | None] = {}
        self.locks = 0

    def checkpoint(self) -> tuple[dict[UUID, Batch], dict[UUID, UUID | None]]:
        return dict(self.rows), dict(self.last_group)

    def rollback_to(self, state: tuple[dict[UUID, Batch], dict[UUID, UUID | None]]) -> None:
        self.rows, self.last_group = dict(state[0]), dict(state[1])

    async def lock(self) -> None:
        self.locks += 1
        await asyncio.sleep(0)

    async def list_active(self) -> list[Batch]:
        return fifo([replace(b) for b in self.rows.values()])

    async def get(self, batch_id: UUID) -> Batch | None:
        row = self.rows.get(batch_id)
        return replace(row) if row else None

    async def add(self, batch: Batch, *, group_id: UUID) -> Batch:
        saved = replace(batch, id=batch.id or uuid4())
        self.rows[saved.pk] = replace(saved)
        self.last_group[saved.pk] = group_id
        return saved

    async def save(self, batch: Batch, *, group_id: UUID) -> None:
        self.rows[batch.pk] = replace(batch)
        self.last_group[batch.pk] = group_id

    async def delete(self, batch_id: UUID) -> None:
        self.rows.pop(batch_id, None)
        self.last_group.pop(batch_id, None)

    async def restore(self, batch: Batch) -> None:
        self.rows[batch.pk] = replace(batch)
        self.last_group[batch.pk] = None

    async def last_groups(self, batch_ids: Sequence[UUID]) -> dict[UUID, UUID | None]:
        return {i: self.last_group[i] for i in batch_ids if i in self.rows}


class InMemoryOperationLog:
    def __init__(self) -> None:
        self.groups: dict[UUID, OperationGroup] = {}

    def checkpoint(self) -> dict[UUID, OperationGroup]:
        return dict(self.groups)

    def rollback_to(self, state: dict[UUID, OperationGroup]) -> None:
        self.groups = dict(state)

    async def add(self, group: OperationGroup) -> None:
        self.groups[group.id] = group

    async def get(self, group_id: UUID) -> OperationGroup | None:
        return self.groups.get(group_id)

    async def latest_for_user(self, user_id: UUID) -> OperationGroup | None:
        mine = [
            group
            for group in reversed(list(self.groups.values()))
            if group.user_id == user_id and group.undone_at is None
        ]
        return max(mine, key=lambda group: group.created_at, default=None)

    async def mark_undone(self, group_id: UUID, *, at: datetime, by: UUID) -> None:
        self.groups[group_id] = replace(self.groups[group_id], undone_at=at)


class InMemoryClarifications:
    def __init__(self) -> None:
        self.rows: dict[UUID, PendingClarification] = {}

    def checkpoint(self) -> dict[UUID, PendingClarification]:
        return dict(self.rows)

    def rollback_to(self, state: dict[UUID, PendingClarification]) -> None:
        self.rows = dict(state)

    async def get(self, user_id: UUID, *, now: datetime) -> PendingClarification | None:
        pending = self.rows.get(user_id)
        return pending if pending is not None and pending.expires_at > now else None

    async def put(self, user_id: UUID, pending: PendingClarification) -> None:
        self.rows[user_id] = pending

    async def delete(self, user_id: UUID) -> None:
        self.rows.pop(user_id, None)


class InMemoryUserLocales:
    def __init__(self, locales: dict[UUID, str] | None = None) -> None:
        self.locales = dict(locales or {})

    async def locale(self, user_id: UUID) -> str | None:
        locale = self.locales.get(user_id)
        return locale if locale in {"ru", "en"} else None


class StaticHouseholdView:
    def __init__(self, context: HouseholdContext | None) -> None:
        self.context = context

    async def current(self) -> HouseholdContext | None:
        return self.context


@dataclass
class KitchenMemory:
    """One household's in-memory state; every tenant in a test shares it."""

    context: HouseholdContext | None
    batches: InMemoryBatches = field(default_factory=InMemoryBatches)
    log: InMemoryOperationLog = field(default_factory=InMemoryOperationLog)
    clarifications: InMemoryClarifications = field(default_factory=InMemoryClarifications)
    locales: InMemoryUserLocales = field(default_factory=InMemoryUserLocales)
    extra: dict[type[object], object] = field(default_factory=dict)
    _lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)


class _MemoryHouseholdView:
    def __init__(self, memory: KitchenMemory) -> None:
        self._memory = memory

    async def current(self) -> HouseholdContext | None:
        return self._memory.context


class _TransactionalUow:
    def __init__(
        self, memory: KitchenMemory, factory: InMemoryUnitOfWorkFactory, user_id: UUID | None
    ) -> None:
        self._memory = memory
        self._inner = factory.for_user(user_id) if user_id is not None else factory.system()

    async def __aenter__(self) -> Self:
        # Serialize the full memory transaction, including clarification-only work.
        # Checkpoint after acquisition so a waiting rollback keeps committed writers.
        await self._memory._lock.acquire()
        try:
            self._state = (
                self._memory.batches.checkpoint(),
                self._memory.log.checkpoint(),
                self._memory.clarifications.checkpoint(),
            )
            await self._inner.__aenter__()
            return self
        except BaseException:
            self._memory._lock.release()
            raise

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        try:
            if exc_type is not None:
                self._memory.batches.rollback_to(self._state[0])
                self._memory.log.rollback_to(self._state[1])
                self._memory.clarifications.rollback_to(self._state[2])
            await self._inner.__aexit__(exc_type, exc, tb)
        finally:
            self._memory._lock.release()

    def repo(self, kind: type[RepoT]) -> RepoT:
        return self._inner.repo(kind)


class KitchenUowFactory:
    def __init__(self, memory: KitchenMemory) -> None:
        self._memory = memory
        self._factory = InMemoryUnitOfWorkFactory(
            {
                HouseholdView: _MemoryHouseholdView(memory),
                BatchRepository: memory.batches,
                OperationLog: memory.log,
                ClarificationRepository: memory.clarifications,
                UserLocales: memory.locales,
                **memory.extra,
            }
        )

    def for_user(self, user_id: UUID) -> _TransactionalUow:
        return _TransactionalUow(self._memory, self._factory, user_id)

    def system(self) -> _TransactionalUow:
        return _TransactionalUow(self._memory, self._factory, None)


def in_memory_uow(memory: KitchenMemory) -> KitchenUowFactory:
    return KitchenUowFactory(memory)
