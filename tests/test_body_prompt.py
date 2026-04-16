import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.fixture
def body_row():
    return {
        "type": "body_composition",
        "source": "vihealth",
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "data": {
            "weight_kg": 79.6, "body_fat_pct": 26.5, "muscle_kg": 54.6,
            "skeletal_muscle_kg": 33.1, "bmr_kcal": 1633,
            "visceral_fat_grade": 8, "body_age": 32, "body_score": 73,
        },
    }


@pytest.mark.asyncio
async def test_get_latest_body_includes_weight(body_row):
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[body_row])), \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        prompt = await build_body_prompt("get_latest_body", {})

    assert "79.6" in prompt
    assert "26.5" in prompt
    assert "get_latest_body" in prompt


@pytest.mark.asyncio
async def test_analyze_body_trend_pulls_cross_context(body_row):
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[body_row])) as mb, \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])) as mr, \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        await build_body_prompt("analyze_body_trend", {})

    assert mb.called
    agents = {c.args[0] for c in mr.call_args_list}
    assert {"nutrition", "workout"}.issubset(agents)


@pytest.mark.asyncio
async def test_body_prompt_handles_empty_data():
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        prompt = await build_body_prompt("get_latest_body", {})

    assert "No body composition" in prompt or "no body" in prompt.lower()
