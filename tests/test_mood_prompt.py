import pytest
from uuid import UUID
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

USER = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def mood_row():
    return {
        "type": "mood",
        "source": "manual",
        "recorded_at": datetime(2026, 4, 16, 20, 30, tzinfo=timezone.utc),
        "data": {
            "mood_score": 6, "energy": 5, "stress": 7, "valence": "neu",
            "tags": ["anxiety", "tired"], "raw_text": "устал и тревожно",
            "source_skill": "log_mood",
        },
    }


@pytest.mark.asyncio
async def test_log_mood_prompt_requests_strict_json():
    with patch("agents.mood.app.prompt.fetch_mood_logs", new=AsyncMock(return_value=[])), \
         patch("agents.mood.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.mood.app.prompt import build_mood_prompt
        prompt = await build_mood_prompt(
            "log_mood", {"user_id": str(USER), "message": "устал"}
        )

    assert "JSON" in prompt or "json" in prompt
    assert "mood_score" in prompt
    assert "energy" in prompt
    assert "stress" in prompt
    assert "valence" in prompt
    assert "tags" in prompt
    assert "устал" in prompt


@pytest.mark.asyncio
async def test_analyze_mood_prompt_shows_history(mood_row):
    with patch("agents.mood.app.prompt.fetch_mood_logs", new=AsyncMock(return_value=[mood_row])), \
         patch("agents.mood.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.mood.app.prompt import build_mood_prompt
        prompt = await build_mood_prompt(
            "analyze_mood",
            {"user_id": str(USER), "message": "как я в этом неделю"},
        )

    assert "mood_score=6" in prompt
    assert "stress=7" in prompt
    assert "analyze_mood" in prompt
    assert "anxiety" in prompt


@pytest.mark.asyncio
async def test_recommendations_prompt_pulls_history(mood_row):
    with patch("agents.mood.app.prompt.fetch_mood_logs", new=AsyncMock(return_value=[mood_row])) as mf, \
         patch("agents.mood.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.mood.app.prompt import build_mood_prompt
        await build_mood_prompt(
            "get_mood_recommendations",
            {"user_id": str(USER), "message": "что делать"},
        )

    assert mf.called


@pytest.mark.asyncio
async def test_empty_history_handled():
    with patch("agents.mood.app.prompt.fetch_mood_logs", new=AsyncMock(return_value=[])), \
         patch("agents.mood.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.mood.app.prompt import build_mood_prompt
        prompt = await build_mood_prompt(
            "analyze_mood", {"user_id": str(USER), "message": "trend"}
        )

    assert "no mood entries" in prompt.lower() or "not enough" in prompt.lower()
