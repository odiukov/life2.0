# tests/test_workout_tasks.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_log_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Workout logged: strength session, 60 min."
                        mock_peers.return_value = {}

                        from agents.workout.app.tasks import handle_task
                        result = await handle_task("log_workout", {"type": "strength", "duration_min": 60})

    assert result.status.state == "completed"
    assert "Workout logged" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_analyze_workout_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Your training volume increased 15% this week."
                        mock_peers.return_value = {}

                        from agents.workout.app.tasks import handle_task
                        result = await handle_task("analyze_workout", {})

    assert result.status.state == "completed"
    assert "training" in result.artifacts[0].parts[0].text.lower()


@pytest.mark.asyncio
async def test_handle_get_workout_recommendations_returns_completed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Rest day recommended based on recent load."
                        mock_peers.return_value = {}

                        from agents.workout.app.tasks import handle_task
                        result = await handle_task("get_recommendations", {})

    assert result.status.state == "completed"
    assert result.artifacts[0].parts[0].text == "Rest day recommended based on recent load."


@pytest.mark.asyncio
async def test_handle_unknown_workout_task_returns_failed():
    from agents.workout.app.tasks import handle_task
    result = await handle_task("fly_to_moon", {})
    assert result.status.state == "failed"
    assert "Unknown task" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_peer_artifacts_kwarg_bypasses_fetch():
    """When peer_artifacts kwarg is provided, fetch_peer_artifacts is NOT called."""
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked prompt"
                        mock_claude.return_value = "Grouped analysis."
                        pre_fetched = {"sleep": "slept 7h", "nutrition": "2000 kcal"}

                        from agents.workout.app.tasks import handle_task
                        await handle_task("analyze_workout", {}, peer_artifacts=pre_fetched)

    mock_peers.assert_not_called()
    assert mock_prompt.call_args.args[2] == pre_fetched


@pytest.mark.asyncio
async def test_handle_workout_task_exception_returns_failed():
    with patch("agents.workout.app.tasks.build_workout_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.workout.app.tasks.run_claude") as mock_claude:
            with patch("agents.workout.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.workout.app.tasks.upsert_memory", new_callable=AsyncMock):
                    with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peers:
                        mock_prompt.return_value = "mocked"
                        mock_claude.side_effect = RuntimeError("Claude unavailable")
                        mock_peers.return_value = {}

                        from agents.workout.app.tasks import handle_task
                        result = await handle_task("analyze_workout", {})

    assert result.status.state == "failed"
    assert "Claude unavailable" in result.artifacts[0].parts[0].text
