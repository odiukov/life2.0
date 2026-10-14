from __future__ import annotations

from typing import Protocol
from uuid import UUID

from medication.domain.medication import Medication


class DuplicateMedication(Exception):
    """An active medication with this name already exists."""


class MedicationRepository(Protocol):
    async def active(self) -> list[Medication]: ...

    async def add(self, med: Medication) -> UUID: ...

    async def archive(self, medication_id: UUID) -> bool: ...
