"""Completion and streaks per local day; weekly habits skip their off days."""

from __future__ import annotations

from collections.abc import Iterable, Mapping, Sequence
from datetime import date, timedelta
from zoneinfo import ZoneInfo

from habits.domain.habit import Habit, HabitCheck, Kind

MAX_DAYS = 400


def by_day(checks: Iterable[HabitCheck], zone: ZoneInfo) -> dict[date, list[HabitCheck]]:
    out: dict[date, list[HabitCheck]] = {}
    for c in checks:
        out.setdefault(c.at.astimezone(zone).date(), []).append(c)
    return out


def today_total(habit: Habit, checks: Sequence[HabitCheck]) -> float:
    return sum(c.value for c in checks if c.value is not None)


def day_complete(habit: Habit, checks: Sequence[HabitCheck]) -> bool:
    if not checks:
        return False
    if habit.kind is Kind.BOOLEAN:
        return any(c.completed for c in checks)
    total = today_total(habit, checks)
    target = habit.target_value or 0
    return total >= target if target > 0 else total > 0


def current_streak(habit: Habit, days: Mapping[date, Sequence[HabitCheck]], today: date) -> int:
    """Due days completed in a row up to today; an incomplete today is still pending, not a break."""
    cursor = today
    if habit.is_due(today) and not day_complete(habit, days.get(today, [])):
        cursor = today - timedelta(days=1)
    streak = 0
    for _ in range(MAX_DAYS):
        if not habit.is_due(cursor):
            cursor -= timedelta(days=1)
            continue
        if not day_complete(habit, days.get(cursor, [])):
            break
        streak += 1
        cursor -= timedelta(days=1)
    return streak


def longest_streak(
    habit: Habit, days: Mapping[date, Sequence[HabitCheck]], start: date, end: date
) -> int:
    best = run = 0
    cursor = start
    while cursor <= end:
        if habit.is_due(cursor):
            if day_complete(habit, days.get(cursor, [])):
                run += 1
                best = max(best, run)
            elif cursor != end:  # today still pending does not break the run
                run = 0
        cursor += timedelta(days=1)
    return best
