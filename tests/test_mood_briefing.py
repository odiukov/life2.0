import pytest
from unittest.mock import AsyncMock, MagicMock, patch


def _mock_row(data: dict):
    row = MagicMock()
    row.__getitem__ = lambda self, k: data[k]
    return row


@pytest.mark.asyncio
async def test_get_yesterday_metrics_includes_mood_when_present():
    mock_pool = AsyncMock()
    sleep_row = _mock_row({
        "duration_seconds": 26580, "deep_sleep_seconds": 6300,
        "hrv_weekly_avg": None, "score": None,
    })
    mood_row = _mock_row({
        "count": 2, "avg_score": 6.5, "avg_stress": 5.0, "avg_energy": 6.0,
        "last_valence": "neu", "last_tags": ["tired", "focused"],
        "first_score": 7, "last_score": 6,
    })
    # sleep, workout (None), nutrition (None), mood
    mock_pool.fetchrow = AsyncMock(side_effect=[sleep_row, None, None, mood_row])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits:
        mock_habits.return_value = []
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["mood"] is not None
    assert result["mood"]["avg_score"] == 6.5
    assert result["mood"]["count"] == 2
    assert "tired" in result["mood"]["last_tags"]


@pytest.mark.asyncio
async def test_get_yesterday_metrics_mood_none_when_empty():
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(side_effect=[None, None, None, None])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits:
        mock_habits.return_value = []
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["mood"] is None


def test_format_message_renders_mood_block():
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Thu 17 Apr",
        "sleep": None, "workout": None, "nutrition": None,
        "mood": {
            "count": 2, "avg_score": 6.5, "avg_stress": 5.0, "avg_energy": 6.0,
            "last_valence": "neu", "last_tags": ["tired"],
            "first_score": 7, "last_score": 6,
        },
    }
    out = format_message(metrics, insight=None)
    assert "Mood" in out
    assert "6.5" in out
    assert "tired" in out


def test_format_message_skips_mood_block_when_missing():
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Thu 17 Apr",
        "sleep": None, "workout": None, "nutrition": None, "mood": None,
    }
    out = format_message(metrics, insight=None)
    assert "Mood" not in out
