"""Ports owned by the kitchen agent."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from kitchen.domain.model import Batch


@dataclass(frozen=True, slots=True)
class HouseholdContext:
    household_id: UUID
    timezone: str
    members: Mapping[UUID, str]

    def zone(self) -> ZoneInfo:
        try:
            return ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            return ZoneInfo("UTC")

    def today(self, now: datetime) -> date:
        return now.astimezone(self.zone()).date()


class HouseholdView(Protocol):
    async def current(self) -> HouseholdContext | None:
        """The actor's household (from the tenant), or None without a membership."""
        ...


class BatchRepository(Protocol):
    async def lock(self) -> None:
        """Lock the household captured by HouseholdView.current until UoW exit.

        Use public.household_lock(uuid) (hashtextextended(uuid::text, 0)) so
        membership transfers serialize with inventory reads and mutations.
        The caller revalidates HouseholdView.current after acquisition; do not
        silently switch the lock to a newly observed household.
        """
        ...

    async def list_active(self) -> list[Batch]:
        """Active batches ordered by expiry, then insertion time."""
        ...

    async def get(self, batch_id: UUID) -> Batch | None: ...

    async def add(self, batch: Batch, *, group_id: UUID) -> Batch: ...

    async def save(self, batch: Batch, *, group_id: UUID) -> None: ...

    async def delete(self, batch_id: UUID) -> None: ...

    async def restore(self, batch: Batch) -> None:
        """Insert or overwrite keeping `batch.id`; clears the last group id."""
        ...

    async def last_groups(self, batch_ids: Sequence[UUID]) -> dict[UUID, UUID | None]:
        """The group that last changed each batch; missing batches are absent."""
        ...


@dataclass(frozen=True, slots=True)
class LoggedChange:
    op_type: str
    batch_id: UUID
    before: dict[str, object] | None
    after: dict[str, object]


@dataclass(frozen=True, slots=True)
class OperationGroup:
    id: UUID
    user_id: UUID
    created_at: datetime
    source: str
    changes: tuple[LoggedChange, ...]
    undone_at: datetime | None = None


class OperationLog(Protocol):
    async def add(self, group: OperationGroup) -> None: ...

    async def get(self, group_id: UUID) -> OperationGroup | None: ...

    async def mark_undone(self, group_id: UUID, *, at: datetime, by: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class PendingClarification:
    text: str
    ref: str
    reason: str
    candidates: tuple[str, ...]
    expires_at: datetime


class ClarificationRepository(Protocol):
    async def get(self, user_id: UUID, *, now: datetime) -> PendingClarification | None:
        """Expired rows count as absent."""
        ...

    async def put(self, user_id: UUID, pending: PendingClarification) -> None:
        """Replaces any pending clarification of this user in this household."""
        ...

    async def delete(self, user_id: UUID) -> None: ...


@dataclass(frozen=True, slots=True)
class MatchCandidate:
    key: str
    score: float  # 0..100


class TextMatcher(Protocol):
    def rank(self, query: str, choices: Sequence[str], *, limit: int) -> list[MatchCandidate]: ...
