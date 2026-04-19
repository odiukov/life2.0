"""Per-chat Telegram thread-id helpers.

Thread id format: ``tg-{chat_id}-{YYYY-MM-DD}-v{reset_count}`` with date in
Europe/Kyiv. Reset counter is process-memory only — bot restarts lose it,
which is acceptable for a single-user personal project (a second /new fixes
any surprise).
"""
from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo

_TZ = ZoneInfo("Europe/Kyiv")
_reset_counts: dict[int, int] = {}


def compute_thread_id(chat_id: int, now: datetime | None = None) -> str:
    """Return the current thread id for a Telegram chat.

    Pass ``now`` to pin the date for tests; production code passes None.
    """
    moment = now if now is not None else datetime.now(_TZ)
    date_str = moment.astimezone(_TZ).strftime("%Y-%m-%d")
    version = _reset_counts.get(chat_id, 0)
    return f"tg-{chat_id}-{date_str}-v{version}"


def bump_reset_count(chat_id: int) -> int:
    """Increment and return the reset counter for ``chat_id``."""
    _reset_counts[chat_id] = _reset_counts.get(chat_id, 0) + 1
    return _reset_counts[chat_id]
