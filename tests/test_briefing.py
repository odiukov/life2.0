# tests/test_briefing.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date


@pytest.mark.asyncio
async def test_get_yesterday_metrics_all_domains():
    """Returns sleep, workout, nutrition when all data present."""
    mock_pool = AsyncMock()
    # sleep row
    sleep_row = MagicMock()
    sleep_row.__getitem__ = lambda self, k: {
        "duration_seconds": 26580, "deep_sleep_seconds": 6300,
        "hrv_weekly_avg": 62, "score": 78,
    }[k]
    # workout row: aggregated over the day
    workout_row = MagicMock()
    workout_row.__getitem__ = lambda self, k: {
        "total_calories": 1240, "total_distance_meters": 14200,
        "activity_count": 1, "first_name": "Long run", "first_type": "running",
    }[k]
    # nutrition row: summed meals
    nutrition_row = MagicMock()
    nutrition_row.__getitem__ = lambda self, k: {
        "kcal": 2850.0, "protein_g": 148.0, "carbs_g": 320.0, "fat_g": 95.0,
    }[k]
    mock_pool.fetchrow = AsyncMock(side_effect=[sleep_row, workout_row, nutrition_row])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["sleep"]["duration_seconds"] == 26580
    assert result["sleep"]["deep_sleep_seconds"] == 6300
    assert result["sleep"]["hrv"] == 62
    assert result["workout"]["total_calories"] == 1240
    assert result["workout"]["total_distance_meters"] == 14200
    assert result["nutrition"]["kcal"] == 2850.0
    assert result["nutrition"]["protein_g"] == 148.0
    assert isinstance(result["date"], str)


@pytest.mark.asyncio
async def test_get_yesterday_metrics_missing_workout():
    """Returns None for workout when no activity logged."""
    mock_pool = AsyncMock()
    sleep_row = MagicMock()
    sleep_row.__getitem__ = lambda self, k: {
        "duration_seconds": 26580, "deep_sleep_seconds": 6300,
        "hrv_weekly_avg": None, "score": None,
    }[k]
    mock_pool.fetchrow = AsyncMock(side_effect=[sleep_row, None, None])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["sleep"] is not None
    assert result["workout"] is None
    assert result["nutrition"] is None


@pytest.mark.asyncio
async def test_get_yesterday_metrics_no_data():
    """Returns all None when no records for yesterday."""
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["sleep"] is None
    assert result["workout"] is None
    assert result["nutrition"] is None


def test_format_message_all_domains():
    """Message includes all three domain lines when all data present."""
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Mon 14 Apr",
        "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300, "hrv": 62, "score": 78},
        "workout": {"total_calories": 1240, "total_distance_meters": 14200,
                    "activity_count": 1, "first_name": "Long run", "first_type": "running"},
        "nutrition": {"kcal": 2850, "protein_g": 148, "carbs_g": 320, "fat_g": 95},
    }
    msg = format_message(metrics, insight="Take it easy today.")
    assert "🌅" in msg
    assert "Mon 14 Apr" in msg
    assert "Sleep:" in msg
    assert "Workout:" in msg
    assert "Nutrition:" in msg
    assert "💡" in msg
    assert "Take it easy today." in msg
    # Spot-check metric formatting
    assert "7h" in msg        # 26580s = 7h 23m
    assert "1h" in msg        # deep sleep
    assert "HRV 62" in msg
    assert "14.2 km" in msg
    assert "1,240 kcal" in msg or "1240 kcal" in msg
    assert "2,850 kcal" in msg or "2850 kcal" in msg


def test_format_message_missing_workout():
    """Workout line omitted when workout is None."""
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Tue 15 Apr",
        "sleep": {"duration_seconds": 28800, "deep_sleep_seconds": 5400, "hrv": None, "score": None},
        "workout": None,
        "nutrition": None,
    }
    msg = format_message(metrics, insight=None)
    assert "Workout:" not in msg
    assert "Nutrition:" not in msg
    assert "Sleep:" in msg
    assert "💡" not in msg  # no insight line when insight is None


def test_format_message_no_insight():
    """No 💡 line when insight is None."""
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Wed 16 Apr",
        "sleep": {"duration_seconds": 25200, "deep_sleep_seconds": 4500, "hrv": 55, "score": 70},
        "workout": None,
        "nutrition": None,
    }
    msg = format_message(metrics, insight=None)
    assert "💡" not in msg
