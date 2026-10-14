"""In-memory HabitRepository with the same contract as the SQL one."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID, uuid4

from habits.application.ports import DuplicateHabit
from habits.domain.habit import Habit


class InMemoryHabits:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.rows: dict[UUID, Habit] = {}
        self.archived: set[UUID] = set()

    async def active(self) -> list[Habit]:
        live = [h for hid, h in self.rows.items() if hid not in self.archived]
        return sorted(
            live, key=lambda h: (h.created_at or datetime.min.replace(tzinfo=UTC), str(h.id))
        )

    async def add(self, habit: Habit) -> UUID:
        if any(h.name == habit.name for h in await self.active()):
            raise DuplicateHabit(habit.name)
        hid = uuid4()
        self.rows[hid] = replace(habit, id=hid, created_at=datetime.now(UTC))
        return hid

    async def archive(self, habit_id: UUID) -> bool:
        if habit_id not in self.rows or habit_id in self.archived:
            return False
        self.archived.add(habit_id)
        return True
