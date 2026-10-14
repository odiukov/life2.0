"""MedicationRepository over the `medications` table (row-level security by user_id)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared.schema.tables import medications
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from medication.application.ports import DuplicateMedication, MedicationRepository
from medication.domain.medication import Medication

_TENANT = text("NULLIF(current_setting('app.user_id', true), '')::uuid")


class SqlMedicationRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def active(self) -> list[Medication]:
        rows = await self._conn.execute(
            select(medications)
            .where(medications.c.archived_at.is_(None))
            .order_by(medications.c.created_at, medications.c.id)
        )
        return [Medication(r.id, r.name, r.dose, r.schedule, r.notes, r.created_at) for r in rows]

    async def add(self, med: Medication) -> UUID:
        statement = (
            insert(medications)
            .values(
                user_id=_TENANT,
                name=med.name,
                dose=med.dose,
                schedule=med.schedule,
                notes=med.notes,
            )
            .returning(medications.c.id)
        )
        try:
            async with self._conn.begin_nested():
                return UUID(str((await self._conn.execute(statement)).scalar_one()))
        except IntegrityError as exc:
            if getattr(
                exc.orig, "sqlstate", None
            ) == "23505" and "medications_user_name_active_uniq" in str(exc.orig):
                raise DuplicateMedication(med.name) from exc
            raise

    async def archive(self, medication_id: UUID) -> bool:
        result = await self._conn.execute(
            update(medications)
            .where(medications.c.id == medication_id, medications.c.archived_at.is_(None))
            .values(archived_at=datetime.now(UTC))
        )
        return bool(result.rowcount)


def medication_repositories() -> dict[type[Any], Callable[[AsyncConnection], Any]]:
    return {MedicationRepository: SqlMedicationRepository}
