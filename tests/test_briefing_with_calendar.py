"""Briefing rendering with the new calendar block."""
from __future__ import annotations


def _base_metrics(calendar=None):
    return {
        "date": "Fri 17 Apr",
        "sleep": None,
        "workout": None,
        "nutrition": None,
        "mood": None,
        "habits": None,
        "calendar": calendar,
    }


def test_format_message_renders_calendar_line_when_present():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(calendar={
        "events_count": 3,
        "morning_count": 2,
        "afternoon_count": 1,
        "evening_count": 0,
        "busiest_hour": "10:00-11:00",
        "first_free_slot_start": "13:30",
        "first_free_slot_len_min": 90,
        "all_day_events": [],
    })
    out = format_message(m, insight=None)
    assert "📅 Today:" in out
    assert "3 meetings" in out
    assert "2 AM" in out and "1 PM" in out
    assert "10:00-11:00" in out
    assert "13:30" in out
    assert "1h30m" in out


def test_format_message_renders_all_day_override():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(calendar={
        "events_count": 0,
        "morning_count": 0, "afternoon_count": 0, "evening_count": 0,
        "busiest_hour": None,
        "first_free_slot_start": None,
        "first_free_slot_len_min": None,
        "all_day_events": ["Vacation"],
    })
    out = format_message(m, insight=None)
    assert "📅 All day: Vacation" in out
    assert "meetings" not in out


def test_format_message_omits_calendar_when_none():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(calendar=None)
    out = format_message(m, insight=None)
    assert "📅" not in out


def test_format_message_places_calendar_after_habits_before_insight():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(calendar={
        "events_count": 1, "morning_count": 1, "afternoon_count": 0, "evening_count": 0,
        "busiest_hour": "09:00-10:00", "first_free_slot_start": "10:00",
        "first_free_slot_len_min": 120, "all_day_events": [],
    })
    m["habits"] = {
        "completed_yesterday": 2, "expected_yesterday": 2,
        "top_streaks": [], "missed_names": [],
        "today_items": [{"name": "med", "done": False}],
        "today_names": ["med"],
    }
    out = format_message(m, insight="Stay hydrated")

    hab = out.index("Habits yesterday")
    cal = out.index("📅 Today:")
    ins = out.index("💡")
    assert hab < cal < ins
