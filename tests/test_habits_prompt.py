import pytest
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone


@pytest.fixture
def habit_row():
    return {
        "id": "abc-123",
        "name": "meditation",
        "kind": "quantitative",
        "cadence_type": "daily",
        "cadence_days": None,
        "target_value": 20,
        "unit": "min",
        "created_at": datetime(2026, 4, 10, tzinfo=timezone.utc),
    }


@pytest.fixture
def check_row():
    return {
        "type": "habit",
        "source": "telegram",
        "recorded_at": datetime(2026, 4, 16, 8, 0, tzinfo=timezone.utc),
        "data": {
            "habit_id": "abc-123",
            "name": "meditation",
            "completed": True,
            "value": 15,
            "unit": "min",
            "raw_text": "/habit meditation 15min",
            "source_skill": "log_habit_check",
        },
    }


@pytest.mark.asyncio
async def test_define_prompt_requests_strict_json_with_kebab_case_rule():
    with patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])):
        from agents.habits.app.prompt import build_habits_prompt
        prompt = await build_habits_prompt(
            "define_habit",
            {"message": "медитация 20 минут каждый день"},
        )
    lower = prompt.lower()
    assert "json" in lower
    assert "kebab" in lower or "hyphen" in lower
    assert "boolean" in lower and "quantitative" in lower
    assert "cadence_type" in prompt
    assert "медитация" in prompt


@pytest.mark.asyncio
async def test_analyze_prompt_shows_check_history(habit_row, check_row):
    with patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[habit_row])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[check_row])):
        from agents.habits.app.prompt import build_habits_prompt
        prompt = await build_habits_prompt(
            "analyze_habit", {"message": "how am I doing"}
        )
    assert "meditation" in prompt
    assert "15" in prompt  # value
    assert "analyze_habit" in prompt


@pytest.mark.asyncio
async def test_analyze_prompt_handles_empty_history(habit_row):
    with patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[habit_row])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[])):
        from agents.habits.app.prompt import build_habits_prompt
        prompt = await build_habits_prompt("analyze_habit", {"message": "trend?"})
    assert "not enough" in prompt.lower() or "no check-ins" in prompt.lower()


@pytest.mark.asyncio
async def test_streak_prompt_is_deterministic_shape():
    with patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])):
        from agents.habits.app.prompt import build_habits_prompt
        prompt = await build_habits_prompt("get_streak_summary", {"message": "/habits"})
    assert "get_streak_summary" in prompt or "streak" in prompt.lower()
