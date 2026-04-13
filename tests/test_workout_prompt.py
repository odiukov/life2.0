import pytest
from unittest.mock import AsyncMock, patch, call


@pytest.mark.asyncio
async def test_build_workout_prompt_contains_task_name():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt("analyze_workout", {"message": "how am I doing?"})

    assert "analyze_workout" in result
    assert "workout" in result.lower()


@pytest.mark.asyncio
async def test_build_workout_prompt_queries_both_agents():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            await build_workout_prompt("get_recommendations", {})

    assert mock_logs.call_count == 2
    agents_queried = [c.args[0] for c in mock_logs.call_args_list]
    assert "workout" in agents_queried
    assert "nutrition" in agents_queried


@pytest.mark.asyncio
async def test_build_workout_prompt_shows_no_logs_fallback():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt("log_workout", {})

    assert "No recent workout logs" in result
    assert "No recent nutrition logs" in result
