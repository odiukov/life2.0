import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_build_nutrition_prompt_contains_task_name():
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            with patch("agents.nutrition.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[]):
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
            with patch("agents.nutrition.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[]):
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
            with patch("agents.nutrition.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[]):
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
            with patch("agents.nutrition.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[]):
                mock_logs.return_value = []
                mock_mem.return_value = []

                from agents.nutrition.app.prompt import build_nutrition_prompt
                result = await build_nutrition_prompt("log_meal", {"raw_text": "греческий йогурт"})

    assert "греческий йогурт" in result


@pytest.mark.asyncio
async def test_build_nutrition_prompt_formats_yazio_logs():
    """Yazio logs show product names and macros, not raw JSON."""
    from datetime import datetime, timezone

    yazio_log = {
        "type": "meal",
        "source": "yazio",
        "recorded_at": datetime(2026, 4, 12, 12, 0, 0, tzinfo=timezone.utc),
        "data": {
            "meal_type": "lunch",
            "items": [
                {"name": "Chicken breast", "amount_g": 200,
                 "kcal": 220, "protein_g": 41.0, "carbs_g": 0.0, "fat_g": 4.8}
            ],
            "totals": {"kcal": 220, "protein_g": 41.0, "carbs_g": 0.0, "fat_g": 4.8},
            "date": "2026-04-12",
        },
    }

    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs:
        with patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem:
            with patch("agents.nutrition.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[]):
                mock_logs.side_effect = lambda agent, limit: (
                    [yazio_log] if agent == "nutrition" else []
                )
                mock_mem.return_value = []

                from agents.nutrition.app.prompt import build_nutrition_prompt
                result = await build_nutrition_prompt("analyze_nutrition", {})

    assert "Chicken breast" in result
    assert "220" in result   # kcal
    assert "41" in result    # protein
    assert "lunch" in result


@pytest.mark.asyncio
async def test_nutrition_prompt_includes_latest_body_row():
    from datetime import datetime, timezone

    body_row = {
        "type": "body_composition",
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "data": {"weight_kg": 79.6, "bmr_kcal": 1633, "body_fat_pct": 26.5},
        "source": "vihealth",
    }
    with patch("agents.nutrition.app.prompt.fetch_recent_logs", new_callable=AsyncMock) as mock_logs, \
         patch("agents.nutrition.app.prompt.search_memories", new_callable=AsyncMock) as mock_mem, \
         patch("agents.nutrition.app.prompt.fetch_body_logs", new_callable=AsyncMock, return_value=[body_row]):
        mock_logs.return_value = []
        mock_mem.return_value = []

        from agents.nutrition.app.prompt import build_nutrition_prompt
        result = await build_nutrition_prompt("get_recommendations", {})

    assert "1633" in result
    assert "79.6" in result
