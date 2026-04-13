# tests/test_sleep_tasks.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_analyze_sleep_returns_completed():
    with patch("agents.sleep.app.tasks.build_sleep_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.sleep.app.tasks.run_claude") as mock_claude:
            with patch("agents.sleep.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.sleep.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "You slept 7 hours on average."

                    from agents.sleep.app.tasks import handle_task
                    result = await handle_task("analyze_sleep", {})

    assert result.status.state == "completed"
    assert "You slept" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_unknown_task_returns_failed():
    from agents.sleep.app.tasks import handle_task
    result = await handle_task("unknown_task", {})
    assert result.status.state == "failed"
    assert "Unknown task" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_sleep_task_has_artifact_name():
    with patch("agents.sleep.app.tasks.build_sleep_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.sleep.app.tasks.run_claude") as mock_claude:
            with patch("agents.sleep.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.sleep.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked"
                    mock_claude.return_value = "analysis result"

                    from agents.sleep.app.tasks import handle_task
                    result = await handle_task("log_sleep", {})

    assert result.artifacts[0].name == "analysis"
    assert result.id != ""
