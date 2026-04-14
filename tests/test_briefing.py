# tests/test_briefing.py
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import date
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_get_yesterday_metrics_all_domains():
    """Returns sleep, workout, nutrition when all data present."""
    mock_pool = AsyncMock()
    # sleep row
    sleep_row = MagicMock()
    sleep_row.__getitem__ = lambda self, k: {
        "duration_seconds": 26580, "deep_sleep_seconds": 6300,
        "hrv_weekly_avg": 62, "score": 78,
    }[k]
    # workout row: aggregated over the day
    workout_row = MagicMock()
    workout_row.__getitem__ = lambda self, k: {
        "total_calories": 1240, "total_distance_meters": 14200,
        "activity_count": 1, "first_name": "Long run", "first_type": "running",
    }[k]
    # nutrition row: summed meals
    nutrition_row = MagicMock()
    nutrition_row.__getitem__ = lambda self, k: {
        "kcal": 2850.0, "protein_g": 148.0, "carbs_g": 320.0, "fat_g": 95.0,
    }[k]
    mock_pool.fetchrow = AsyncMock(side_effect=[sleep_row, workout_row, nutrition_row])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["sleep"]["duration_seconds"] == 26580
    assert result["sleep"]["deep_sleep_seconds"] == 6300
    assert result["sleep"]["hrv"] == 62
    assert result["workout"]["total_calories"] == 1240
    assert result["workout"]["total_distance_meters"] == 14200
    assert result["nutrition"]["kcal"] == 2850.0
    assert result["nutrition"]["protein_g"] == 148.0
    assert isinstance(result["date"], str)


@pytest.mark.asyncio
async def test_get_yesterday_metrics_missing_workout():
    """Returns None for workout when no activity logged."""
    mock_pool = AsyncMock()
    sleep_row = MagicMock()
    sleep_row.__getitem__ = lambda self, k: {
        "duration_seconds": 26580, "deep_sleep_seconds": 6300,
        "hrv_weekly_avg": None, "score": None,
    }[k]
    mock_pool.fetchrow = AsyncMock(side_effect=[sleep_row, None, None])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["sleep"] is not None
    assert result["workout"] is None
    assert result["nutrition"] is None


@pytest.mark.asyncio
async def test_get_yesterday_metrics_no_data():
    """Returns all None when no records for yesterday."""
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["sleep"] is None
    assert result["workout"] is None
    assert result["nutrition"] is None


def test_format_message_all_domains():
    """Message includes all three domain lines when all data present."""
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Mon 14 Apr",
        "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300, "hrv": 62, "score": 78},
        "workout": {"total_calories": 1240, "total_distance_meters": 14200,
                    "activity_count": 1, "first_name": "Long run", "first_type": "running"},
        "nutrition": {"kcal": 2850, "protein_g": 148, "carbs_g": 320, "fat_g": 95},
    }
    msg = format_message(metrics, insight="Take it easy today.")
    assert "🌅" in msg
    assert "Mon 14 Apr" in msg
    assert "Sleep:" in msg
    assert "Workout:" in msg
    assert "Nutrition:" in msg
    assert "💡" in msg
    assert "Take it easy today." in msg
    # Spot-check metric formatting
    assert "7h" in msg        # 26580s = 7h 23m
    assert "1h" in msg        # deep sleep
    assert "HRV 62" in msg
    assert "14.2 km" in msg
    assert "1,240 kcal" in msg or "1240 kcal" in msg
    assert "2,850 kcal" in msg or "2850 kcal" in msg


def test_format_message_missing_workout():
    """Workout line omitted when workout is None."""
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Tue 15 Apr",
        "sleep": {"duration_seconds": 28800, "deep_sleep_seconds": 5400, "hrv": None, "score": None},
        "workout": None,
        "nutrition": None,
    }
    msg = format_message(metrics, insight=None)
    assert "Workout:" not in msg
    assert "Nutrition:" not in msg
    assert "Sleep:" in msg
    assert "💡" not in msg  # no insight line when insight is None


# NOTE: test_sleep_briefing_task_returns_completed removed — the old
# `agents.sleep.app.tasks.handle_task` entrypoint was replaced by the A2A
# executor pattern. Executor-level coverage lives in tests/test_sleep_executor.py.


@pytest.mark.asyncio
async def test_workout_briefing_task_returns_completed():
    """Workout agent handles 'briefing' task and returns completed with text."""
    with patch("agents.workout.app.tasks.run_claude") as mock_claude:
        with patch("agents.workout.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock) as mock_peer:
            mock_claude.return_value = "You ran 14.2 km yesterday burning 1,240 kcal."

            from agents.workout.app.tasks import handle_task
            result = await handle_task("briefing", {
                "total_calories": 1240,
                "total_distance_meters": 14200,
                "first_name": "Long run",
                "first_type": "running",
                "activity_count": 1,
            })

    assert result.status.state == "completed"
    assert result.artifacts[0].parts[0].text != ""
    mock_peer.assert_not_called()


@pytest.mark.asyncio
async def test_nutrition_briefing_task_returns_completed():
    """Nutrition agent handles 'briefing' task and returns completed with text."""
    with patch("agents.nutrition.app.tasks.run_claude") as mock_claude:
        with patch("agents.nutrition.app.tasks.fetch_peer_artifacts", new_callable=AsyncMock):
            with patch("agents.nutrition.app.tasks._trigger_yazio_sync", new_callable=AsyncMock):
                mock_claude.return_value = "You ate 2,850 kcal with 148g protein yesterday."

                from agents.nutrition.app.tasks import handle_task
                result = await handle_task("briefing", {
                    "kcal": 2850,
                    "protein_g": 148,
                    "carbs_g": 320,
                    "fat_g": 95,
                })

    assert result.status.state == "completed"
    assert result.artifacts[0].parts[0].text != ""


def test_format_message_no_insight():
    """No 💡 line when insight is None."""
    from orchestrator.app.briefing import format_message
    metrics = {
        "date": "Wed 16 Apr",
        "sleep": {"duration_seconds": 25200, "deep_sleep_seconds": 4500, "hrv": 55, "score": 70},
        "workout": None,
        "nutrition": None,
    }
    msg = format_message(metrics, insight=None)
    assert "💡" not in msg


@pytest.mark.asyncio
async def test_call_agents_for_briefing_returns_summaries():
    """Calls all agents in parallel and returns domain summaries."""
    async def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={
            "artifacts": [{"name": "briefing", "parts": [{"type": "text", "text": "summary text"}]}]
        })
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = mock_post

    agents = {
        "sleep": {"url": "http://agent-sleep:8001"},
        "workout": {"url": "http://agent-workout:8002"},
        "nutrition": {"url": "http://agent-nutrition:8003"},
    }
    metrics = {
        "date": "Mon 14 Apr",
        "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300, "hrv": 62, "score": 78},
        "workout": {"total_calories": 1240, "total_distance_meters": 14200,
                    "activity_count": 1, "first_name": "Long run", "first_type": "running"},
        "nutrition": {"kcal": 2850, "protein_g": 148, "carbs_g": 320, "fat_g": 95},
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        from orchestrator.app.briefing import call_agents_for_briefing
        summaries = await call_agents_for_briefing(agents, metrics)

    assert "sleep" in summaries
    assert "workout" in summaries
    assert "nutrition" in summaries
    assert summaries["sleep"] == "summary text"


@pytest.mark.asyncio
async def test_call_agents_for_briefing_skips_missing_domain():
    """Skips agent call when that domain's metrics are None."""
    async def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json = MagicMock(return_value={
            "artifacts": [{"name": "briefing", "parts": [{"type": "text", "text": "sleep summary"}]}]
        })
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = mock_post

    agents = {
        "sleep": {"url": "http://agent-sleep:8001"},
        "workout": {"url": "http://agent-workout:8002"},
    }
    metrics = {
        "date": "Mon 14 Apr",
        "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300, "hrv": None, "score": None},
        "workout": None,
        "nutrition": None,
    }

    with patch("httpx.AsyncClient", return_value=mock_client):
        from orchestrator.app.briefing import call_agents_for_briefing
        summaries = await call_agents_for_briefing(agents, metrics)

    assert "sleep" in summaries
    assert summaries["sleep"] == "sleep summary"
    assert "workout" not in summaries
    assert "nutrition" not in summaries


def test_generate_insight_calls_claude():
    """generate_insight passes metrics + summaries to Claude and returns text."""
    with patch("orchestrator.app.briefing.run_claude", return_value="Rest today.") as mock_claude:
        from orchestrator.app.briefing import generate_insight
        result = generate_insight(
            metrics={"date": "Mon 14 Apr", "sleep": {"hrv": 50}, "workout": {"total_calories": 1240}, "nutrition": None},
            summaries={"sleep": "Short on deep sleep.", "workout": "Heavy run."},
        )

    assert result == "Rest today."
    assert mock_claude.called
    prompt = mock_claude.call_args[0][0]
    assert "Short on deep sleep" in prompt
    assert "Heavy run" in prompt


@pytest.mark.asyncio
async def test_send_telegram_message_posts_to_api():
    """send_telegram_message POSTs to Telegram sendMessage endpoint."""
    async def mock_post(url, **kwargs):
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        return resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(side_effect=mock_post)

    with patch("httpx.AsyncClient", return_value=mock_client):
        from orchestrator.app.briefing import send_telegram_message
        await send_telegram_message("TOKEN123", "CHAT456", "Hello!")

    call_args = mock_client.post.call_args
    assert "TOKEN123" in call_args[0][0]
    assert call_args[1]["json"]["chat_id"] == "CHAT456"
    assert call_args[1]["json"]["text"] == "Hello!"


@pytest.mark.asyncio
async def test_run_briefing_skipped_when_no_data():
    """run_briefing returns skipped when no health data for yesterday."""
    with patch("orchestrator.app.briefing.get_yesterday_metrics", new_callable=AsyncMock) as mock_metrics:
        mock_metrics.return_value = {"date": "Mon 14 Apr", "sleep": None, "workout": None, "nutrition": None}
        with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat"}):
            from orchestrator.app.briefing import run_briefing
            result = await run_briefing({})

    assert result["status"] == "skipped"
    assert "no data" in result["reason"]


@pytest.mark.asyncio
async def test_run_briefing_skipped_when_telegram_not_configured():
    """run_briefing returns skipped when TELEGRAM env vars are missing."""
    import os
    env_without_telegram = {k: v for k, v in os.environ.items() if k not in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID")}
    with patch.dict("os.environ", env_without_telegram, clear=True):
        from orchestrator.app.briefing import run_briefing
        result = await run_briefing({})

    assert result["status"] == "skipped"
    assert "telegram not configured" in result["reason"]


@pytest.mark.asyncio
async def test_run_briefing_sends_metrics_only_when_claude_fails():
    """run_briefing sends message without insight when Claude call fails."""
    with patch("orchestrator.app.briefing.get_yesterday_metrics", new_callable=AsyncMock) as mock_metrics:
        mock_metrics.return_value = {
            "date": "Mon 14 Apr",
            "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300, "hrv": 62, "score": 78},
            "workout": None,
            "nutrition": None,
        }
        with patch("orchestrator.app.briefing.call_agents_for_briefing", new_callable=AsyncMock) as mock_agents:
            mock_agents.return_value = {"sleep": "Good sleep."}
            with patch("orchestrator.app.briefing.generate_insight", side_effect=RuntimeError("Claude down")):
                with patch("orchestrator.app.briefing.send_telegram_message", new_callable=AsyncMock) as mock_send:
                    with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat"}):
                        from orchestrator.app.briefing import run_briefing
                        result = await run_briefing({})

    assert result["status"] == "sent"
    # Message was sent despite Claude failing
    mock_send.assert_called_once()
    sent_text = mock_send.call_args[0][2]
    assert "🌅" in sent_text
    assert "💡" not in sent_text  # no insight since Claude failed


@pytest.mark.asyncio
async def test_run_briefing_returns_error_when_telegram_fails():
    """run_briefing returns error when Telegram send fails."""
    with patch("orchestrator.app.briefing.get_yesterday_metrics", new_callable=AsyncMock) as mock_metrics:
        mock_metrics.return_value = {
            "date": "Mon 14 Apr",
            "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300, "hrv": 62, "score": 78},
            "workout": None,
            "nutrition": None,
        }
        with patch("orchestrator.app.briefing.call_agents_for_briefing", new_callable=AsyncMock) as mock_agents:
            mock_agents.return_value = {}
            with patch("orchestrator.app.briefing.send_telegram_message", new_callable=AsyncMock) as mock_send:
                mock_send.side_effect = Exception("network error")
                with patch.dict("os.environ", {"TELEGRAM_BOT_TOKEN": "tok", "TELEGRAM_CHAT_ID": "chat"}):
                    from orchestrator.app.briefing import run_briefing
                    result = await run_briefing({})

    assert result["status"] == "error"
    assert "network error" in result["reason"]


@pytest.mark.asyncio
async def test_post_briefing_endpoint_returns_sent():
    """POST /briefing returns {"status": "sent"} when briefing succeeds."""
    with patch("orchestrator.app.main.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"status": "sent"}
        with patch("orchestrator.app.registry.get_registry", return_value={}):
            from orchestrator.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/briefing")

    assert resp.status_code == 200
    assert resp.json()["status"] == "sent"


@pytest.mark.asyncio
async def test_post_briefing_endpoint_returns_skipped():
    """POST /briefing returns {"status": "skipped"} when no data available."""
    with patch("orchestrator.app.main.run_briefing", new_callable=AsyncMock) as mock_run:
        mock_run.return_value = {"status": "skipped", "reason": "no data for yesterday"}
        with patch("orchestrator.app.registry.get_registry", return_value={}):
            from orchestrator.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/briefing")

    assert resp.status_code == 200
    assert resp.json()["status"] == "skipped"
