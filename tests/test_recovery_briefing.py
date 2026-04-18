"""Briefing rendering with the new recovery block."""
import pytest
from unittest.mock import AsyncMock, patch


def _base_metrics(recovery=None):
    return {
        "date": "Fri 18 Apr",
        "sleep": None,
        "workout": None,
        "nutrition": None,
        "mood": None,
        "habits": None,
        "recovery": recovery,
        "calendar": None,
    }


def test_format_message_renders_recovery_line_when_bucket_present():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(recovery={
        "bucket": "recovered",
        "top3": [
            {"label": "HRV", "value": 45, "dir": "↑", "delta": "+5%"},
            {"label": "stress", "value": 28, "dir": "↓", "delta": "-12%"},
            {"label": "body battery", "value": 85, "dir": "↑", "delta": "+8%"},
        ],
    })
    out = format_message(m, insight=None)
    assert "🔋 Recovery: recovered" in out
    assert "HRV 45" in out
    assert "stress 28" in out
    assert "body battery 85" in out


def test_format_message_renders_depleted_bucket():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(recovery={
        "bucket": "depleted",
        "top3": [
            {"label": "HRV", "value": 38, "dir": "↓", "delta": "-8%"},
            {"label": "stress", "value": 62, "dir": "↑", "delta": "+20%"},
            {"label": "RHR", "value": 63, "dir": "↑", "delta": "+4%"},
        ],
    })
    out = format_message(m, insight=None)
    assert "🔋 Recovery: depleted" in out


def test_format_message_omits_recovery_when_none():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(recovery=None)
    out = format_message(m, insight=None)
    assert "🔋" not in out


def test_format_message_places_recovery_between_habits_and_calendar():
    from orchestrator.app.briefing import format_message
    m = _base_metrics(recovery={
        "bucket": "neutral",
        "top3": [{"label": "HRV", "value": 44, "dir": "·", "delta": None}],
    })
    m["habits"] = {
        "completed_yesterday": 2, "expected_yesterday": 2,
        "top_streaks": [], "missed_names": [],
        "today_items": [{"name": "med", "done": False}],
        "today_names": ["med"],
    }
    m["calendar"] = {
        "events_count": 1, "morning_count": 1, "afternoon_count": 0, "evening_count": 0,
        "busiest_hour": None, "first_free_slot_start": None, "first_free_slot_len_min": None,
        "all_day_events": [],
    }
    out = format_message(m, insight=None)
    hab_idx = out.index("Habits yesterday")
    rec_idx = out.index("🔋 Recovery:")
    cal_idx = out.index("📅 Today:")
    assert hab_idx < rec_idx < cal_idx


@pytest.mark.asyncio
async def test_get_yesterday_metrics_populates_recovery_key():
    from unittest.mock import MagicMock
    from orchestrator.app import db as odb

    fake_shape = {
        "bucket": "recovered",
        "top3": [{"label": "HRV", "value": 45, "dir": "↑", "delta": "+5%"}],
    }
    mock_pool = MagicMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)
    with patch.object(odb, "get_pool", return_value=mock_pool), \
         patch.object(odb, "fetch_recovery_shape", new=AsyncMock(return_value=fake_shape)), \
         patch.object(odb, "fetch_active_habits", new=AsyncMock(return_value=[])), \
         patch.object(odb, "fetch_habit_logs", new=AsyncMock(return_value=[])):
        metrics = await odb.get_yesterday_metrics()
    assert metrics["recovery"] == fake_shape


@pytest.mark.asyncio
async def test_fetch_recovery_shape_returns_none_on_unknown_bucket():
    from orchestrator.app import recovery_context
    empty_metrics = {}
    with patch.object(recovery_context, "fetch_recovery_metrics",
                      new=AsyncMock(return_value=empty_metrics)):
        from datetime import date
        result = await recovery_context.fetch_recovery_shape(date(2026, 4, 17))
    assert result is None


@pytest.mark.asyncio
async def test_fetch_recovery_shape_returns_shape_on_recovered_bucket():
    from orchestrator.app import recovery_context
    today = "2026-04-17"
    metrics = {
        today: {"hrv": 50, "rhr": 55, "stress": 20, "bb_min": 40, "bb_max": 90, "sleep_score": 85},
        "2026-04-16": {"hrv": 44, "rhr": 60, "stress": 40, "bb_min": 20, "bb_max": 80, "sleep_score": 75},
        "2026-04-15": {"hrv": 45, "rhr": 60, "stress": 42, "bb_min": 22, "bb_max": 78, "sleep_score": 76},
        "2026-04-14": {"hrv": 45, "rhr": 60, "stress": 40, "bb_min": 22, "bb_max": 80, "sleep_score": 80},
        "2026-04-13": {"hrv": 44, "rhr": 61, "stress": 41, "bb_min": 20, "bb_max": 79, "sleep_score": 77},
    }
    with patch.object(recovery_context, "fetch_recovery_metrics",
                      new=AsyncMock(return_value=metrics)):
        from datetime import date
        result = await recovery_context.fetch_recovery_shape(date(2026, 4, 17))
    assert result is not None
    assert result["bucket"] == "recovered"
    assert len(result["top3"]) >= 1
