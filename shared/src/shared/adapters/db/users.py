from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.ports.users import SUPPORTED_LOCALES, UserSettings, resolve_zone
from shared.schema.tables import users


class SqlUserSettings:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID) -> UserSettings:
        row = (
            await self._conn.execute(
                select(users.c.timezone, users.c.preferences).where(users.c.id == user_id)
            )
        ).one_or_none()
        if row is None:
            return UserSettings(resolve_zone(None), None)
        prefs = row.preferences if isinstance(row.preferences, Mapping) else {}
        locale = prefs.get("locale")
        return UserSettings(
            resolve_zone(row.timezone),
            locale if isinstance(locale, str) and locale in SUPPORTED_LOCALES else None,
        )
