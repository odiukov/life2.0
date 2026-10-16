"""Two short nights in a row: worth an early night today."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, timedelta

SHORT_NIGHT_S = 6 * 3600


def short_streak(nights: Mapping[date, int], today: date) -> bool:
    """`nights` maps a wake-up local date to the longest session of that day, in seconds."""
    last, before = nights.get(today), nights.get(today - timedelta(days=1))
    return last is not None and before is not None and max(last, before) < SHORT_NIGHT_S
