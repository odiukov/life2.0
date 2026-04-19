"""Hermetic unit tests for telegram_bot.app.threads.

The helpers accept an injectable `now` datetime so we don't need freezegun
or monkeypatching to test TZ + date boundaries.
"""
from __future__ import annotations

import re
from datetime import datetime, timezone
from zoneinfo import ZoneInfo


def test_compute_thread_id_format():
    from telegram_bot.app.threads import compute_thread_id
    # Kyiv noon on 2026-04-19 for chat 123
    now = datetime(2026, 4, 19, 12, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    tid = compute_thread_id(123, now=now)
    assert re.fullmatch(r"tg-123-2026-04-19-v\d+", tid)


def test_compute_thread_id_uses_kyiv_tz_not_utc():
    from telegram_bot.app.threads import compute_thread_id
    # 23:30 UTC on 2026-04-18 == 02:30 Kyiv on 2026-04-19 (EEST +03:00 in summer, +02:00 in winter).
    # April 19 is during EEST (summer time in Ukraine), so Kyiv is UTC+3.
    # 23:30 UTC on April 18 == 02:30 Kyiv on April 19.
    now = datetime(2026, 4, 18, 23, 30, tzinfo=timezone.utc)
    tid = compute_thread_id(1, now=now)
    assert "-2026-04-19-" in tid, f"expected Kyiv date 2026-04-19, got {tid}"


def test_compute_thread_id_stable_same_day_same_chat():
    from telegram_bot.app.threads import compute_thread_id
    now1 = datetime(2026, 4, 19, 9, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    now2 = datetime(2026, 4, 19, 21, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert compute_thread_id(777, now=now1) == compute_thread_id(777, now=now2)


def test_compute_thread_id_changes_across_days():
    from telegram_bot.app.threads import compute_thread_id
    d1 = datetime(2026, 4, 19, 12, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    d2 = datetime(2026, 4, 20, 12, 0, tzinfo=ZoneInfo("Europe/Kyiv"))
    assert compute_thread_id(42, now=d1) != compute_thread_id(42, now=d2)


def test_bump_reset_count_increments_only_target_chat():
    from telegram_bot.app.threads import bump_reset_count, compute_thread_id
    now = datetime(2026, 4, 19, 12, 0, tzinfo=ZoneInfo("Europe/Kyiv"))

    before_a = compute_thread_id(100, now=now)
    before_b = compute_thread_id(200, now=now)

    new_count = bump_reset_count(100)
    assert new_count == 1

    after_a = compute_thread_id(100, now=now)
    after_b = compute_thread_id(200, now=now)

    assert after_a != before_a, "thread id for chat 100 should change after bump"
    assert after_b == before_b, "thread id for chat 200 should be unaffected"
    assert after_a.endswith("-v1")
    assert before_a.endswith("-v0")


def test_bump_reset_count_repeated_increments():
    from telegram_bot.app.threads import bump_reset_count
    # Use a unique chat_id so previous tests' state doesn't interfere.
    assert bump_reset_count(999_001) == 1
    assert bump_reset_count(999_001) == 2
    assert bump_reset_count(999_001) == 3
