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
