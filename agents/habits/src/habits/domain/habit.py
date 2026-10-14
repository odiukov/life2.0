"""Habit definitions and check-ins (stored as health_logs type='habit' with the legacy keys)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum
from typing import Any, Protocol
from uuid import UUID

WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")


class Kind(StrEnum):
    BOOLEAN = "boolean"
    QUANTITATIVE = "quantitative"


class Cadence(StrEnum):
    DAILY = "daily"
    WEEKLY = "weekly"


@dataclass(frozen=True, slots=True)
class Habit:
    id: UUID | None
    name: str
    kind: Kind
    cadence: Cadence
    cadence_days: tuple[str, ...]
    target_value: float | None
    unit: str | None
    created_at: datetime | None

    def is_due(self, day: date) -> bool:
        return self.cadence is Cadence.DAILY or WEEKDAYS[day.weekday()] in self.cadence_days


class _Row(Protocol):
    @property
    def recorded_at(self) -> datetime: ...

    @property
    def data(self) -> Mapping[str, Any]: ...


def _num(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class HabitCheck:
    habit_id: str
    at: datetime
    value: float | None
    unit: str | None
    note: str | None
    completed: bool = True

    @classmethod
    def from_row(cls, row: _Row) -> HabitCheck:
        d = row.data
        return cls(
            habit_id=str(d.get("habit_id") or ""),
            at=row.recorded_at,
            value=_num(d.get("value")),
            unit=d.get("unit") if isinstance(d.get("unit"), str) else None,
            note=d.get("note") if isinstance(d.get("note"), str) else None,
            completed=bool(d.get("completed", True)),
        )


def check_data(
    habit: Habit, raw_text: str, value: float | None, unit: str | None, note: str | None
) -> dict[str, object]:
    """The legacy row shape (the orchestrator dashboard reads it)."""
    data: dict[str, object] = {
        "habit_id": str(habit.id),
        "name": habit.name,
        "completed": True,
        "raw_text": raw_text,
        "source_skill": "log_habit_check",
    }
    if value is not None:
        data["value"] = value
    if unit:
        data["unit"] = unit
    if note:
        data["note"] = note
    return data
