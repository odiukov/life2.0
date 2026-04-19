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
    mock_pool.fetchrow = AsyncMock(side_effect=[sleep_row, workout_row, nutrition_row, None])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits, \
         patch("orchestrator.app.db.fetch_body_logs", new_callable=AsyncMock) as mock_body:
        mock_habits.return_value = []
        mock_body.return_value = []
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
    mock_pool.fetchrow = AsyncMock(side_effect=[sleep_row, None, None, None])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits, \
         patch("orchestrator.app.db.fetch_body_logs", new_callable=AsyncMock) as mock_body:
        mock_habits.return_value = []
        mock_body.return_value = []
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["sleep"] is not None
    assert result["workout"] is None
    assert result["nutrition"] is None


@pytest.mark.asyncio
async def test_get_yesterday_metrics_sleep_query_drops_end_window():
    """Sleep query must filter only by lower bound so it can return last night's
    sleep — the session starts after yesterday-Kyiv-evening, so a strict
    [yesterday, today) window misses it. Regression test for off-by-one-night bug."""
    from datetime import timezone
    captured: dict = {}

    async def fake_fetchrow(sql: str, *args, **kwargs):
        if "agent = 'sleep'" in sql:
            captured["sql"] = sql
            captured["args"] = args
        return None

    mock_pool = AsyncMock()
    mock_pool.fetchrow = fake_fetchrow

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits, \
         patch("orchestrator.app.db.fetch_body_logs", new_callable=AsyncMock) as mock_body:
        mock_habits.return_value = []
        mock_body.return_value = []
        from orchestrator.app.db import get_yesterday_metrics
        await get_yesterday_metrics()

    sql = captured["sql"]
    assert "ORDER BY recorded_at DESC" in sql
    assert "LIMIT 1" in sql
    # only a lower bound — no upper bound that would cut off last night
    assert "recorded_at < " not in sql
    # exactly one bind param (the lower bound)
    assert len(captured["args"]) == 1


@pytest.mark.asyncio
async def test_get_yesterday_metrics_no_data():
    """Returns all None when no records for yesterday."""
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(return_value=None)

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits, \
         patch("orchestrator.app.db.fetch_body_logs", new_callable=AsyncMock) as mock_body:
        mock_habits.return_value = []
        mock_body.return_value = []
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
    assert "📊" in msg
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


# NOTE: test_workout_briefing_task_returns_completed removed — the old
# `agents.workout.app.tasks.handle_task` entrypoint was replaced by the A2A
# executor pattern. Executor-level coverage lives in tests/test_workout_executor.py.


# NOTE: test_nutrition_briefing_task_returns_completed removed — the old
# `agents.nutrition.app.tasks.handle_task` entrypoint was replaced by the A2A
# executor pattern. Executor-level coverage lives in tests/test_nutrition_executor.py.


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


def _briefing_task_with_text(text: str):
    """Build a completed Task carrying a single text artifact."""
    from a2a.types import Artifact, Part, Task, TaskState, TaskStatus, TextPart

    artifact = Artifact(
        artifact_id="a1",
        name="briefing",
        parts=[Part(root=TextPart(text=text))],
    )
    return Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.completed),
        artifacts=[artifact],
    )


def _make_fake_briefing_client():
    """Fake A2A Client whose send_message sentinels text off metadata.params['sentinel']."""
    async def _send_message(message):
        params = (message.metadata or {}).get("params", {})
        sentinel = params.get("sentinel", "default-summary")
        yield (_briefing_task_with_text(sentinel), None)

    client = AsyncMock()
    client.send_message = lambda message: _send_message(message)
    return client


@pytest.mark.asyncio
async def test_call_agents_for_briefing_returns_summaries():
    """Fan-out: each agent gets its own params and summary is keyed by agent name."""
    fake_client = _make_fake_briefing_client()

    agents = {
        "sleep": {"url": "http://agent-sleep:8001"},
        "workout": {"url": "http://agent-workout:8002"},
        "nutrition": {"url": "http://agent-nutrition:8003"},
    }
    metrics = {
        "date": "Mon 14 Apr",
        "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300,
                  "hrv": 62, "score": 78, "sentinel": "sleep-summary"},
        "workout": {"total_calories": 1240, "total_distance_meters": 14200,
                    "activity_count": 1, "first_name": "Long run",
                    "first_type": "running", "sentinel": "workout-summary"},
        "nutrition": {"kcal": 2850, "protein_g": 148, "carbs_g": 320,
                      "fat_g": 95, "sentinel": "nutrition-summary"},
    }

    with patch("orchestrator.app.briefing.get_client", AsyncMock(return_value=fake_client)):
        from orchestrator.app.briefing import call_agents_for_briefing
        summaries = await call_agents_for_briefing(agents, metrics)

    assert summaries == {
        "sleep": "sleep-summary",
        "workout": "workout-summary",
        "nutrition": "nutrition-summary",
    }


@pytest.mark.asyncio
async def test_call_agents_for_briefing_skips_missing_domain():
    """Domains whose metrics are None result in no A2A call."""
    call_urls: list[str] = []

    async def _send_message(message):
        params = (message.metadata or {}).get("params", {})
        yield (_briefing_task_with_text(params.get("sentinel", "x")), None)

    fake_client = AsyncMock()
    fake_client.send_message = lambda message: _send_message(message)

    async def fake_get_client(url: str):
        call_urls.append(url)
        return fake_client

    agents = {
        "sleep": {"url": "http://agent-sleep:8001"},
        "workout": {"url": "http://agent-workout:8002"},
    }
    metrics = {
        "date": "Mon 14 Apr",
        "sleep": {"duration_seconds": 26580, "deep_sleep_seconds": 6300,
                  "hrv": None, "score": None, "sentinel": "sleep-only"},
        "workout": None,
        "nutrition": None,
    }

    with patch("orchestrator.app.briefing.get_client", fake_get_client):
        from orchestrator.app.briefing import call_agents_for_briefing
        summaries = await call_agents_for_briefing(agents, metrics)

    assert summaries == {"sleep": "sleep-only"}
    assert call_urls == ["http://agent-sleep:8001"]


@pytest.mark.asyncio
async def test_generate_insight_calls_claude():
    """generate_insight passes metrics + summaries to the LLM and returns text."""
    fake_llm = MagicMock()
    fake_llm.ainvoke = AsyncMock(return_value=MagicMock(content="Rest today."))
    with patch("orchestrator.app.briefing._LLM", fake_llm):
        from orchestrator.app.briefing import generate_insight
        result = await generate_insight(
            metrics={"date": "Mon 14 Apr", "sleep": {"hrv": 50}, "workout": {"total_calories": 1240}, "nutrition": None},
            summaries={"sleep": "Short on deep sleep.", "workout": "Heavy run."},
        )

    assert result == "Rest today."
    assert fake_llm.ainvoke.called
    call_args = fake_llm.ainvoke.call_args[0][0]
    prompt = call_args[0].content
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
    assert "📊" in sent_text
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


from datetime import datetime, timedelta, timezone


@pytest.mark.asyncio
async def test_get_yesterday_metrics_body_latest_and_recent():
    """metrics['body'] = {latest: {...}, recent_90d: [...]} from fetch_body_logs."""
    now = datetime(2026, 4, 18, 7, 15, tzinfo=timezone.utc)
    rows = [
        {"type": "body_composition", "recorded_at": now,
         "data": {"weight_kg": 82.3, "body_fat_pct": 18.4,
                  "lean_mass_kg": 62.1, "bmi": 24.1}, "source": "garmin"},
        {"type": "body_composition", "recorded_at": now - timedelta(days=7),
         "data": {"weight_kg": 80.5, "body_fat_pct": 17.9,
                  "lean_mass_kg": 61.8, "bmi": 23.7}, "source": "garmin"},
    ]
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(side_effect=[None, None, None, None])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits, \
         patch("orchestrator.app.db.fetch_body_logs", new_callable=AsyncMock) as mock_body:
        mock_habits.return_value = []
        mock_body.return_value = rows
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    body = result["body"]
    assert body is not None
    assert body["latest"]["weight_kg"] == 82.3
    assert body["latest"]["body_fat_pct"] == 18.4
    assert body["latest"]["recorded_at"] == now
    assert len(body["recent_90d"]) == 2
    assert body["recent_90d"][1]["weight_kg"] == 80.5


@pytest.mark.asyncio
async def test_get_yesterday_metrics_body_none_when_no_rows():
    """metrics['body'] is None when fetch_body_logs returns []."""
    mock_pool = AsyncMock()
    mock_pool.fetchrow = AsyncMock(side_effect=[None, None, None, None])

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool), \
         patch("orchestrator.app.db.fetch_active_habits", new_callable=AsyncMock) as mock_habits, \
         patch("orchestrator.app.db.fetch_body_logs", new_callable=AsyncMock) as mock_body:
        mock_habits.return_value = []
        mock_body.return_value = []
        from orchestrator.app.db import get_yesterday_metrics
        result = await get_yesterday_metrics()

    assert result["body"] is None
