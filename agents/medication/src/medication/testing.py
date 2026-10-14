"""In-memory MedicationRepository with the same contract as the SQL one."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from medication.application.ports import DuplicateMedication
from medication.domain.medication import Medication


class InMemoryMedications:
    def __init__(self) -> None:
        self.rows: dict[UUID, Medication] = {}
        self.archived: set[UUID] = set()
        self._tick = 0

    async def active(self) -> list[Medication]:
        live = [m for mid, m in self.rows.items() if mid not in self.archived]
        return sorted(
            live, key=lambda m: (m.created_at or datetime.min.replace(tzinfo=UTC), str(m.id))
        )

    async def add(self, med: Medication) -> UUID:
        if any(m.name == med.name for m in await self.active()):
            raise DuplicateMedication(med.name)
        mid = uuid4()
        self._tick += 1
        self.rows[mid] = replace(
            med, id=mid, created_at=datetime(2026, 1, 1, tzinfo=UTC) + timedelta(seconds=self._tick)
        )
        return mid

    async def archive(self, medication_id: UUID) -> bool:
        if medication_id not in self.rows or medication_id in self.archived:
            return False
        self.archived.add(medication_id)
        return True
