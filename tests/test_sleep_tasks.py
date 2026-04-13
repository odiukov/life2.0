import pytest
from unittest.mock import AsyncMock, patch, MagicMock


@pytest.mark.asyncio
async def test_handle_analyze_sleep_returns_response():
    with patch("agents.sleep.app.tasks.build_sleep_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.sleep.app.tasks.run_claude") as mock_claude:
            with patch("agents.sleep.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.sleep.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "You slept 7 hours on average."

                    from agents.sleep.app.tasks import handle_task
                    result = await handle_task("analyze_sleep", {})

    assert result["status"] == "completed"
    assert "You slept" in result["output"]


@pytest.mark.asyncio
async def test_handle_unknown_task_returns_error():
    from agents.sleep.app.tasks import handle_task
    result = await handle_task("unknown_task", {})
    assert result["status"] == "error"
    assert "unknown" in result["output"].lower()
