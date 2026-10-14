"""Workouts from Garmin, HealthKit and chat."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from zoneinfo import ZoneInfo


class _Row(Protocol):
    @property
    def recorded_at(self) -> datetime: ...

    @property
    def data(self) -> Mapping[str, Any]: ...

    @property
    def source(self) -> str: ...


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class Workout:
    recorded_at: datetime
    activity_type: str
    name: str
    duration_s: int | None
    distance_m: float | None
    calories: float | None
    avg_hr: float | None
    max_hr: float | None
    effort: int | None
    source: str

    @classmethod
    def from_row(cls, row: _Row) -> Workout:
        d = row.data
        duration = _num(d.get("duration_seconds"))
        effort = _num(d.get("effort"))
        return cls(
            recorded_at=row.recorded_at,
            activity_type=str(d.get("activity_type") or "unknown"),
            name=str(d.get("name") or ""),
            duration_s=int(duration) if duration is not None else None,
            distance_m=_num(d.get("distance_meters")),
            calories=_num(d.get("calories")),
            avg_hr=_num(d.get("avg_hr")),
            max_hr=_num(d.get("max_hr")),
            effort=int(effort) if effort is not None else None,
            source=row.source,
        )

    def to_data(self) -> dict[str, object]:
        data: dict[str, object] = {"activity_type": self.activity_type, "name": self.name}
        if self.duration_s is not None:
            data["duration_seconds"] = self.duration_s
        if self.distance_m is not None:
            data["distance_meters"] = int(self.distance_m)
        if self.effort is not None:
            data["effort"] = self.effort
        return data


def _g(value: float) -> str:
    return str(int(value)) if value.is_integer() else f"{value:g}"


def workout_line(w: Workout, zone: ZoneInfo) -> str:
    parts = [f"- {w.recorded_at.astimezone(zone).date()}", w.source, w.activity_type]
    if w.duration_s:
        parts.append(f"{round(w.duration_s / 60)} min")
    if w.distance_m:
        parts.append(f"{w.distance_m / 1000:.1f} km")
    for label, value in (("kcal", w.calories), ("avg_hr", w.avg_hr), ("max_hr", w.max_hr)):
        if value is not None:
            parts.append(f"{label}={_g(value)}")
    if w.effort is not None:
        parts.append(f"effort={w.effort}/10")
    return " | ".join(parts)


def resolve_start(
    started_at: str | None, duration_minutes: int, now: datetime, zone: ZoneInfo
) -> datetime:
    """UTC start; a stated start later than now means yesterday; no start means now minus duration."""
    if started_at is None:
        return now.astimezone(UTC) - timedelta(minutes=duration_minutes)
    local_now = now.astimezone(zone)
    hh, mm = (int(x) for x in started_at.split(":"))
    start = datetime(local_now.year, local_now.month, local_now.day, hh, mm, tzinfo=zone)
    if start > local_now:
        day = local_now.date() - timedelta(days=1)
        start = datetime(day.year, day.month, day.day, hh, mm, tzinfo=zone)
    return start.astimezone(UTC)
