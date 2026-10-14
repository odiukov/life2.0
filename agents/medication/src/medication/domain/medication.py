"""Tracked medications and intakes (health_logs type='medication_taken', legacy keys)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Medication:
    id: UUID | None
    name: str
    dose: str | None
    schedule: str
    notes: str | None
    created_at: datetime | None


class _Row(Protocol):
    @property
    def recorded_at(self) -> datetime: ...

    @property
    def data(self) -> Mapping[str, Any]: ...


def _text(value: object) -> str | None:
    return value if isinstance(value, str) and value else None


@dataclass(frozen=True, slots=True)
class Intake:
    medication_id: str | None
    name: str
    at: datetime
    dose_at_time: str | None
    note: str | None

    @classmethod
    def from_row(cls, row: _Row) -> Intake:
        d = row.data
        return cls(
            medication_id=_text(d.get("medication_id")),
            name=str(d.get("name") or ""),
            at=row.recorded_at,
            dose_at_time=_text(d.get("dose_at_time")),
            note=_text(d.get("note")),
        )


def intake_data(
    med: Medication, raw_text: str, dose: str | None, note: str | None
) -> dict[str, object]:
    return {
        "name": med.name,
        "medication_id": str(med.id),
        "dose_at_time": dose or med.dose,
        "note": note,
        "raw_text": raw_text,
        "source_skill": "log_medication",
    }
