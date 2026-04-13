# tests/test_nutrition_tasks.py
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_handle_log_meal_returns_completed():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Meal logged: гречка с курицей ~520 ккал, 42г белка."

                    from agents.nutrition.app.tasks import handle_task
                    result = await handle_task("log_meal", {"raw_text": "гречка с курицей"})

    assert result.status.state == "completed"
    assert "Meal logged" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_log_meal_passes_raw_text_in_params():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock) as mock_insert:
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Logged."

                    from agents.nutrition.app.tasks import handle_task
                    await handle_task("log_meal", {"raw_text": "творог с бананом"})

    assert mock_insert.call_args.args[2].get("raw_text") == "творог с бананом"


@pytest.mark.asyncio
async def test_handle_analyze_nutrition_returns_completed():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.return_value = "Your average protein intake is 120g/day."

                    from agents.nutrition.app.tasks import handle_task
                    result = await handle_task("analyze_nutrition", {})

    assert result.status.state == "completed"
    assert "protein" in result.artifacts[0].parts[0].text.lower()


@pytest.mark.asyncio
async def test_handle_unknown_nutrition_task_returns_failed():
    from agents.nutrition.app.tasks import handle_task
    result = await handle_task("order_pizza", {})
    assert result.status.state == "failed"
    assert "Unknown task" in result.artifacts[0].parts[0].text


@pytest.mark.asyncio
async def test_handle_nutrition_task_exception_returns_failed():
    with patch("agents.nutrition.app.tasks.build_nutrition_prompt", new_callable=AsyncMock) as mock_prompt:
        with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
            with patch("agents.nutrition.app.tasks.insert_task", new_callable=AsyncMock):
                with patch("agents.nutrition.app.tasks.upsert_memory", new_callable=AsyncMock):
                    mock_prompt.return_value = "mocked prompt"
                    mock_claude.side_effect = RuntimeError("Claude unavailable")

                    from agents.nutrition.app.tasks import handle_task
                    result = await handle_task("analyze_nutrition", {})

    assert result.status.state == "failed"
    assert "Claude unavailable" in result.artifacts[0].parts[0].text
