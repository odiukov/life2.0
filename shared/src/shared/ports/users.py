"""Per-user settings every agent needs: the time zone that defines "today" and the reply locale."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

SUPPORTED_LOCALES = frozenset({"ru", "en"})


def resolve_zone(name: str | None) -> ZoneInfo:
    if not name:
        return ZoneInfo("UTC")
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return ZoneInfo("UTC")


@dataclass(frozen=True, slots=True)
class UserSettings:
    timezone: ZoneInfo
    locale: str | None

    def today(self, now: datetime) -> date:
        return now.astimezone(self.timezone).date()


class UserSettingsRepository(Protocol):
    async def get(self, user_id: UUID) -> UserSettings:
        """Unknown users and invalid values resolve to UTC and no locale."""
        ...
