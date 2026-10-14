"""Notifications: a per-user inbox (always) and best-effort device push."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Notification:
    kind: str
    title: str
    body: str
    data: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class InboxItem:
    id: UUID
    kind: str
    title: str
    body: str
    data: dict[str, str]
    created_at: datetime
    read_at: datetime | None


class NotificationSender(Protocol):
    async def send(self, recipients: Sequence[UUID], notification: Notification) -> None:
        """Deliver to every recipient's inbox; push is best-effort and never raises."""
        ...


class NotificationInbox(Protocol):
    """Repository over `notifications`, bound to a tenant unit of work."""

    async def add(
        self, user_id: UUID, notification: Notification, *, created_at: datetime
    ) -> UUID: ...

    async def page(self, user_id: UUID, *, before: datetime | None, limit: int) -> list[InboxItem]:
        """Newest first; `before` is exclusive."""
        ...

    async def unread_count(self, user_id: UUID) -> int: ...

    async def mark_read(self, user_id: UUID, notification_id: UUID, *, at: datetime) -> bool:
        """False when the id is unknown (or belongs to someone else)."""
        ...

    async def mark_all_read(self, user_id: UUID, *, at: datetime) -> int: ...


class PushTokens(Protocol):
    """Repository over `push_tokens`, bound to a tenant unit of work."""

    async def upsert(self, user_id: UUID, token: str, platform: str, *, at: datetime) -> None: ...

    async def delete(self, user_id: UUID, token: str) -> None: ...

    async def for_user(self, user_id: UUID) -> list[str]: ...
