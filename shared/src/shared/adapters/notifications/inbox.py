from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from sqlalchemy import func, insert, select, update
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.ports.notifications import InboxItem, Notification
from shared.schema.tables import notifications


def _item(row: Row[Any]) -> InboxItem:
    return InboxItem(
        id=row.id,
        kind=row.kind,
        title=row.title,
        body=row.body,
        data={str(k): str(v) for k, v in (row.data or {}).items()},
        created_at=row.created_at,
        read_at=row.read_at,
    )


class SqlNotificationInbox:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, user_id: UUID, notification: Notification, *, created_at: datetime) -> UUID:
        statement = (
            insert(notifications)
            .values(
                user_id=user_id,
                kind=notification.kind,
                title=notification.title,
                body=notification.body,
                data=dict(notification.data),
                created_at=created_at,
            )
            .returning(notifications.c.id)
        )
        return UUID(str((await self._conn.execute(statement)).scalar_one()))

    async def page(self, user_id: UUID, *, before: datetime | None, limit: int) -> list[InboxItem]:
        query = select(notifications).where(notifications.c.user_id == user_id)
        if before is not None:
            query = query.where(notifications.c.created_at < before)
        query = query.order_by(notifications.c.created_at.desc(), notifications.c.id.desc()).limit(
            limit
        )
        return [_item(r) for r in await self._conn.execute(query)]

    async def unread_count(self, user_id: UUID) -> int:
        query = select(func.count()).where(
            notifications.c.user_id == user_id, notifications.c.read_at.is_(None)
        )
        return int((await self._conn.execute(query)).scalar_one())

    async def mark_read(self, user_id: UUID, notification_id: UUID, *, at: datetime) -> bool:
        found = await self._conn.execute(
            select(notifications.c.id).where(
                notifications.c.id == notification_id, notifications.c.user_id == user_id
            )
        )
        if found.first() is None:
            return False
        await self._conn.execute(
            update(notifications)
            .where(
                notifications.c.id == notification_id,
                notifications.c.user_id == user_id,
                notifications.c.read_at.is_(None),
            )
            .values(read_at=at)
        )
        return True

    async def mark_all_read(self, user_id: UUID, *, at: datetime) -> int:
        result = await self._conn.execute(
            update(notifications)
            .where(notifications.c.user_id == user_id, notifications.c.read_at.is_(None))
            .values(read_at=at)
        )
        return int(result.rowcount or 0)
