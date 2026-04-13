import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_log_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Workout logged: strength session, 60 min."

                    from agents.workout.app.tasks import handle_task
                    result = await handle_task("log_workout", {"type": "strength", "duration_min": 60})

    assert result["status"] == "completed"
    assert "Workout logged" in result["output"]


@pytest.mark.asyncio
async def test_handle_analyze_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Your training volume increased 15% this week."

                    from agents.workout.app.tasks import handle_task
                    result = await handle_task("analyze_workout", {})

    assert result["status"] == "completed"
    assert "training" in result["output"].lower()


@pytest.mark.asyncio
async def test_handle_get_workout_recommendations_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Rest day recommended based on recent load."

                    from agents.workout.app.tasks import handle_task
                    result = await handle_task("get_recommendations", {})

    assert result["status"] == "completed"
    assert result["output"] == "Rest day recommended based on recent load."


@pytest.mark.asyncio
async def test_handle_unknown_workout_task_returns_error():
    from agents.workout.app.tasks import handle_task
    result = await handle_task("fly_to_moon", {})
    assert result["status"] == "error"
    assert "unknown" in result["output"].lower()
