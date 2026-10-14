"""Calendar days in the user's time zone."""

from __future__ import annotations

from datetime import UTC, date, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

_UTC_ZONE = ZoneInfo("UTC")


def resolve_zone(name: object) -> ZoneInfo:
    """The user's zone; anything missing or unknown is treated as UTC."""
    if not isinstance(name, str) or not name:
        return _UTC_ZONE
    try:
        return ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError):
        return _UTC_ZONE


def _require_aware(now: datetime) -> None:
    if now.utcoffset() is None:
        raise ValueError("now must be timezone-aware")


def local_today(now: datetime, zone: ZoneInfo) -> date:
    _require_aware(now)
    return now.astimezone(zone).date()


def day_window(day: date, zone: ZoneInfo) -> tuple[datetime, datetime]:
    """[local midnight, next local midnight) as UTC instants; 23 or 25 hours on DST days."""
    start = datetime.combine(day, time.min, zone)
    end = datetime.combine(day + timedelta(days=1), time.min, zone)
    return start.astimezone(UTC), end.astimezone(UTC)


def resolve_eaten_at(now: datetime, zone: ZoneInfo, eaten_at: time | None) -> datetime:
    """A stated clock time means today, unless it is still in the future: then yesterday."""
    _require_aware(now)
    if eaten_at is None:
        return now.astimezone(UTC)
    local_now = now.astimezone(zone)
    candidate = datetime.combine(local_now.date(), eaten_at, zone)
    if candidate.astimezone(UTC) > now.astimezone(UTC):
        candidate = datetime.combine(local_now.date() - timedelta(days=1), eaten_at, zone)
    return candidate.astimezone(UTC)
