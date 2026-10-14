"""Body composition measurements (ViHealth/LePulse scales, HealthKit)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo


class _Row(Protocol):
    @property
    def recorded_at(self) -> datetime: ...

    @property
    def data(self) -> Mapping[str, Any]: ...

    @property
    def source(self) -> str: ...


def number(value: object) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


@dataclass(frozen=True, slots=True)
class BodyMeasurement:
    recorded_at: datetime
    weight_kg: float | None
    body_fat_pct: float | None
    muscle_kg: float | None
    skeletal_muscle_kg: float | None
    lean_mass_kg: float | None
    bmr_kcal: float | None
    visceral_fat_grade: float | None
    body_age: float | None
    body_score: float | None
    source: str

    @classmethod
    def from_row(cls, row: _Row) -> BodyMeasurement:
        d = row.data
        return cls(
            recorded_at=row.recorded_at,
            weight_kg=number(d.get("weight_kg")),
            body_fat_pct=number(d.get("body_fat_pct")),
            muscle_kg=number(d.get("muscle_kg")),
            skeletal_muscle_kg=number(d.get("skeletal_muscle_kg")),
            lean_mass_kg=number(d.get("lean_mass_kg")),
            bmr_kcal=number(d.get("bmr_kcal")),
            visceral_fat_grade=number(d.get("visceral_fat_grade")),
            body_age=number(d.get("body_age")),
            body_score=number(d.get("body_score")),
            source=row.source,
        )


_FIELDS: tuple[tuple[str, str, str], ...] = (
    ("weight", "weight_kg", "kg"),
    ("fat", "body_fat_pct", "%"),
    ("muscle", "muscle_kg", "kg"),
    ("skeletal_muscle", "skeletal_muscle_kg", "kg"),
    ("bmr", "bmr_kcal", "kcal"),
    ("visceral_fat", "visceral_fat_grade", ""),
    ("body_age", "body_age", ""),
    ("body_score", "body_score", ""),
)


def measurement_line(m: BodyMeasurement, zone: ZoneInfo) -> str:
    day = m.recorded_at.astimezone(zone).date()
    parts = [
        f"{label}={_value(getattr(m, attr))}{unit}"
        for label, attr, unit in _FIELDS
        if getattr(m, attr) is not None
    ]
    return f"- {day} | " + (" | ".join(parts) if parts else "(no metrics)")


def _value(value: float) -> str:
    """Print like the legacy prompt: 82.5 stays 82.5, 7 stays 7, 1800 stays 1800."""
    return str(int(value)) if value.is_integer() else f"{value:g}"
