"""Habits due today that are still unchecked in the evening."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from habits.domain.habit import Habit

HABITS_EVENING_HOUR = 18


def due_unchecked(habits: Sequence[Habit], checked_ids: set[str], today: date) -> list[Habit]:
    return [h for h in habits if h.is_due(today) and str(h.id) not in checked_ids]
