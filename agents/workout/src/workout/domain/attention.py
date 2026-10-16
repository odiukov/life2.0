"""When the user should plan a workout: a regular trainee has gone quiet."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

QUIET_DAYS = 4
MIN_RECENT_DAYS = 2
WINDOW_DAYS = 30


def quiet_days(workout_days: Sequence[date], today: date) -> int | None:
    """Days since the last workout when it is a gap worth flagging, else None."""
    days = set(workout_days)
    if len(days) < MIN_RECENT_DAYS:
        return None
    gap = (today - max(days)).days
    return gap if gap >= QUIET_DAYS else None
