# tests/test_workout_prompt.py
import pytest
from unittest.mock import AsyncMock, patch


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
async def test_build_workout_prompt_queries_only_workout_logs():
    """Workout prompt only queries its own DB logs; nutrition comes from peer_artifacts."""
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            await build_workout_prompt("get_recommendations", {})

    assert mock_logs.call_count == 1
    assert mock_logs.call_args.args[0] == "workout"


@pytest.mark.asyncio
async def test_build_workout_prompt_includes_peer_artifacts():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt(
                "get_recommendations",
                {},
                peer_artifacts={"sleep": "slept 7h avg", "nutrition": "2000 kcal today"},
            )

    assert "slept 7h avg" in result
    assert "2000 kcal today" in result
    assert "sleep-agent" in result
    assert "nutrition-agent" in result


@pytest.mark.asyncio
async def test_build_workout_prompt_shows_no_logs_fallback():
    with patch("agents.workout.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.workout.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.workout.app.prompt import build_workout_prompt
            result = await build_workout_prompt("log_workout", {})

    assert "No recent workout logs" in result
