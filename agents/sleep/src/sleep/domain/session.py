"""Sleep sessions from devices and chat; placing a spoken night on the clock."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo


class _Row(Protocol):
    @property
    def recorded_at(self) -> datetime: ...

    @property
    def data(self) -> Mapping[str, Any]: ...

    @property
    def source(self) -> str: ...


class _Night(Protocol):
    duration_minutes: int | None
    bed_time: str | None
    wake_time: str | None


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    n = _num(value)
    return int(n) if n is not None else None


def _parse(value: object) -> datetime | None:
    if not isinstance(value, str) or not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


@dataclass(frozen=True, slots=True)
class SleepSession:
    start: datetime | None
    end: datetime | None
    duration_s: int | None
    deep_s: int | None
    rem_s: int | None
    light_s: int | None
    awake_s: int | None
    score: int | None
    hrv: float | None
    avg_hr: float | None
    quality: int | None
    source: str
    recorded_at: datetime | None = None

    @classmethod
    def from_row(cls, row: _Row) -> SleepSession:
        d = row.data
        return cls(
            start=_parse(d.get("start_time")) or _parse(d.get("sleep_start")),
            end=_parse(d.get("end_time")) or _parse(d.get("sleep_end")),
            duration_s=_int(d.get("duration_seconds")),
            deep_s=_int(d.get("deep_sleep_seconds")),
            rem_s=_int(d.get("rem_sleep_seconds")),
            light_s=_int(d.get("light_sleep_seconds")),
            awake_s=_int(d.get("awake_seconds")),
            score=_int(d.get("score")),
            hrv=_num(d.get("hrv_weekly_avg")),
            avg_hr=_num(d.get("avg_hr")),
            quality=_int(d.get("quality")),
            source=row.source,
            recorded_at=row.recorded_at,
        )

    def to_data(self) -> dict[str, object]:
        """Garmin's keys, so recovery and analysis read chat sessions with no special case."""
        data: dict[str, object] = {"duration_seconds": self.duration_s}
        if self.start is not None:
            data["start_time"] = self.start.isoformat()
        if self.end is not None:
            data["end_time"] = self.end.isoformat()
        if self.quality is not None:
            data["quality"] = self.quality
        return data


def _hours(seconds: int) -> str:
    return f"{seconds / 3600:.1f}h"


def session_line(s: SleepSession, zone: ZoneInfo) -> str:
    anchor = s.recorded_at or s.start
    parts = [f"- {anchor.astimezone(zone).date() if anchor else '?'}", s.source]
    if s.duration_s:
        parts.append(_hours(s.duration_s))
    for label, seconds in (("deep", s.deep_s), ("rem", s.rem_s), ("awake", s.awake_s)):
        if seconds:
            parts.append(f"{label}={_hours(seconds)}")
    if s.score is not None:
        parts.append(f"score={s.score}")
    if s.hrv is not None:
        parts.append(f"hrv={s.hrv:g}")
    if s.avg_hr is not None:
        parts.append(f"avg_hr={s.avg_hr:g}")
    if s.quality is not None:
        parts.append(f"quality={s.quality}/5")
    return " | ".join(parts)


def _on(day: date, hhmm: str, zone: ZoneInfo) -> datetime:
    hh, mm = (int(x) for x in hhmm.split(":"))
    return datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)


def resolve_session(
    night: _Night, now: datetime, zone: ZoneInfo
) -> tuple[datetime, datetime] | None:
    """Real UTC (start, end) of what the person said, or None when it cannot be placed.

    Durations are computed in UTC: subtracting two datetimes that share one ZoneInfo ignores DST.
    """
    local_now = now.astimezone(zone)
    today = local_now.date()
    minutes = night.duration_minutes
    if night.wake_time is not None:
        end = _on(today, night.wake_time, zone)
        if end > local_now:
            end = _on(today - timedelta(days=1), night.wake_time, zone)
        if night.bed_time is not None:
            start = _on(end.date(), night.bed_time, zone)
            if start >= end:
                start = _on(end.date() - timedelta(days=1), night.bed_time, zone)
        elif minutes is not None:
            start = (end.astimezone(UTC) - timedelta(minutes=minutes)).astimezone(zone)
        else:
            return None
    elif minutes is not None:
        if night.bed_time is not None:
            start = _on(today, night.bed_time, zone)
            if start > local_now:
                start = _on(today - timedelta(days=1), night.bed_time, zone)
            end = (start.astimezone(UTC) + timedelta(minutes=minutes)).astimezone(zone)
        else:
            end = local_now
            start = (end.astimezone(UTC) - timedelta(minutes=minutes)).astimezone(zone)
    else:
        return None
    start_utc, end_utc = start.astimezone(UTC), end.astimezone(UTC)
    if not start_utc < end_utc <= now.astimezone(UTC):
        return None
    return start_utc, end_utc
