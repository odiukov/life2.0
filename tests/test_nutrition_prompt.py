import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_build_nutrition_prompt_contains_task_name():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            result = await build_nutrition_prompt("log_meal", {"raw_text": "овсянка"})

    assert "log_meal" in result
    assert "nutrition" in result.lower()


@pytest.mark.asyncio
async def test_build_nutrition_prompt_queries_both_agents():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            await build_nutrition_prompt("get_recommendations", {})

    assert mock_logs.call_count == 2
    agents_queried = [c.args[0] for c in mock_logs.call_args_list]
    assert "nutrition" in agents_queried
    assert "workout" in agents_queried


@pytest.mark.asyncio
async def test_build_nutrition_prompt_shows_no_logs_fallback():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            result = await build_nutrition_prompt("analyze_nutrition", {})

    assert "No recent nutrition logs" in result
    assert "No recent workout logs" in result


@pytest.mark.asyncio
async def test_build_nutrition_prompt_includes_raw_text_in_params():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            mock_logs.return_value = []
            mock_mem.return_value = []

            from agents.nutrition.app.prompt import build_nutrition_prompt
            result = await build_nutrition_prompt("log_meal", {"raw_text": "греческий йогурт"})

    assert "греческий йогурт" in result
