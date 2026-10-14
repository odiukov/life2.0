from __future__ import annotations

from typing import Protocol
from uuid import UUID

from habits.domain.habit import Habit


class DuplicateHabit(Exception):
    """An active habit with this name already exists."""


class HabitRepository(Protocol):
    async def active(self) -> list[Habit]:
        """Active habits of the tenant, oldest first."""
        ...

    async def add(self, habit: Habit) -> UUID:
        """Raises DuplicateHabit when the name is already active."""
        ...

    async def archive(self, habit_id: UUID) -> bool:
        """False when it was already archived or does not exist."""
        ...
