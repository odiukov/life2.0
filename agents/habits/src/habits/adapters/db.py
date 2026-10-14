"""HabitRepository over the `habits` table (row-level security by user_id)."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from shared.schema.tables import habits
from sqlalchemy import insert, select, text, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncConnection

from habits.application.ports import DuplicateHabit, HabitRepository
from habits.domain.habit import Cadence, Habit, Kind

_TENANT = text("NULLIF(current_setting('app.user_id', true), '')::uuid")


class SqlHabitRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def active(self) -> list[Habit]:
        rows = await self._conn.execute(
            select(habits)
            .where(habits.c.archived_at.is_(None))
            .order_by(habits.c.created_at, habits.c.id)
        )
        return [
            Habit(
                id=r.id,
                name=r.name,
                kind=Kind(r.kind),
                cadence=Cadence(r.cadence_type),
                cadence_days=tuple(r.cadence_days or ()),
                target_value=float(r.target_value) if r.target_value is not None else None,
                unit=r.unit,
                created_at=r.created_at,
            )
            for r in rows
        ]

    async def add(self, habit: Habit) -> UUID:
        statement = (
            insert(habits)
            .values(
                user_id=_TENANT,
                name=habit.name,
                kind=habit.kind.value,
                cadence_type=habit.cadence.value,
                cadence_days=list(habit.cadence_days) or None,
                target_value=habit.target_value,
                unit=habit.unit,
            )
            .returning(habits.c.id)
        )
        try:
            async with self._conn.begin_nested():
                return UUID(str((await self._conn.execute(statement)).scalar_one()))
        except IntegrityError as exc:
            if getattr(
                exc.orig, "sqlstate", None
            ) == "23505" and "habits_user_name_active_uniq" in str(exc.orig):
                raise DuplicateHabit(habit.name) from exc
            raise

    async def archive(self, habit_id: UUID) -> bool:
        result = await self._conn.execute(
            update(habits)
            .where(habits.c.id == habit_id, habits.c.archived_at.is_(None))
            .values(archived_at=datetime.now(UTC))
        )
        return bool(result.rowcount)


def habits_repositories() -> dict[type[Any], Callable[[AsyncConnection], Any]]:
    return {HabitRepository: SqlHabitRepository}
