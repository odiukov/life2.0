"""A regularly taken medication with no intake logged by the evening."""

from __future__ import annotations

from datetime import date, timedelta

MED_EVENING_HOUR = 20
HISTORY_DAYS = 7
MIN_TAKEN_DAYS = 5


def missed_today(taken_days: set[date], today: date) -> bool:
    if today in taken_days:
        return False
    window = {today - timedelta(days=n) for n in range(1, HISTORY_DAYS + 1)}
    return len(taken_days & window) >= MIN_TAKEN_DAYS
