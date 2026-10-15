"""Raw access to `health_logs` shared by every health agent; agents map rows to their own types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class HealthLogRow:
    type: str
    recorded_at: datetime
    data: Mapping[str, Any] = field(default_factory=dict)
    source: str = "chat"
    agent: str = ""


class HealthLogRepository(Protocol):
    async def lock_user(self, user_id: UUID) -> None:
        """Serialize compound health-log writes for this user until transaction exit."""
        ...

    async def insert_once(self, user_id: UUID, row: HealthLogRow) -> bool:
        """Insert without changing an existing dedup key; True only for a new row."""
        ...

    async def recent(
        self,
        user_id: UUID,
        *,
        types: Sequence[str],
        limit: int | None = None,
        since: datetime | None = None,
        until: datetime | None = None,
        agent: str | None = None,
        data_equals: Mapping[str, str] | None = None,
    ) -> list[HealthLogRow]:
        """Newest first. `since` is inclusive and `until` exclusive; `data_equals` matches data->>key = value."""
        ...

    async def add(self, user_id: UUID, row: HealthLogRow) -> datetime:
        """Store the row; on a (user, source, type, recorded_at) clash shift by 1 µs until free."""
        ...

    async def upsert(self, user_id: UUID, row: HealthLogRow) -> bool:
        """Insert, or replace data and agent on a (user, source, type, recorded_at) clash when it differs; True if written."""
        ...
