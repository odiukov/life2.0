from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from uuid import UUID

from sqlalchemy import insert, select, update
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.schema.tables import users


def merge_body_profile(prefs: Mapping[str, Any], changes: Mapping[str, object]) -> dict[str, Any]:
    raw = prefs.get("body_profile")
    body = dict(raw) if isinstance(raw, Mapping) else {}
    for key, value in changes.items():
        if value is None:
            body.pop(key, None)
        else:
            body[key] = value
    return body


class SqlBodyProfiles:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID) -> dict[str, object]:
        prefs = (
            await self._conn.execute(select(users.c.preferences).where(users.c.id == user_id))
        ).scalar_one_or_none()
        raw = prefs.get("body_profile") if isinstance(prefs, Mapping) else None
        return dict(raw) if isinstance(raw, Mapping) else {}

    async def update(self, user_id: UUID, changes: Mapping[str, object]) -> dict[str, object]:
        row = (
            await self._conn.execute(
                select(users.c.preferences).where(users.c.id == user_id).with_for_update()
            )
        ).one_or_none()
        prefs: dict[str, Any] = (
            dict(row.preferences)
            if row is not None and isinstance(row.preferences, Mapping)
            else {}
        )
        body = merge_body_profile(prefs, changes)
        prefs["body_profile"] = body
        if row is None:
            await self._conn.execute(
                insert(users).values(id=user_id, name=f"user:{str(user_id)[:8]}", preferences=prefs)
            )
        else:
            await self._conn.execute(
                update(users).where(users.c.id == user_id).values(preferences=prefs)
            )
        return body
