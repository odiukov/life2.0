# tests/test_briefing_alert_flow.py
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest

pytestmark = pytest.mark.asyncio

from orchestrator.app.alerts import Alert
from orchestrator.app.briefing import compose_alert_brief, build_dashboard


def test_compose_alert_brief_shows_must_see_always():
    metrics = {
        "date": "2026-04-18",
        "sleep": {"duration_seconds": 25200, "deep_sleep_seconds": 5400, "hrv": 54},
        "calendar": {"events_count": 3, "morning_count": 1, "afternoon_count": 2,
                     "evening_count": 0, "all_day_events": [],
                     "busiest_hour": "14:00", "first_free_slot_start": None,
                     "first_free_slot_len_min": None},
    }
    alerts = []
    text = compose_alert_brief(metrics, alerts)
    assert "Sleep:" in text
    assert "3 meetings" in text


def test_compose_alert_brief_shows_alerts():
    metrics = {"date": "2026-04-18", "sleep": None, "calendar": None}
    alerts = [Alert(
        rule_id="medication.missed.2d",
        severity="warn",
        message="missed magnesium 2 days",
        category="wellness",
    )]
    text = compose_alert_brief(metrics, alerts)
    assert "missed magnesium 2 days" in text


def test_compose_alert_brief_quiet_when_no_alerts_no_mustsee():
    metrics = {"date": "2026-04-18", "sleep": None, "calendar": None}
    text = compose_alert_brief(metrics, [])
    assert "all quiet" in text.lower() or "nothing to flag" in text.lower()


def test_build_dashboard_includes_all_shapes():
    metrics = {
        "date": "2026-04-18",
        "sleep": {"duration_seconds": 25200, "deep_sleep_seconds": 5400, "hrv": 54},
        "workout": {"total_distance_meters": 5240, "total_calories": 412,
                    "activity_count": 1, "first_name": "Morning Run", "first_type": "running"},
        "nutrition": {"kcal": 2100, "protein_g": 140, "carbs_g": 220, "fat_g": 75},
    }
    text = build_dashboard(metrics, insight=None)
    assert "Sleep:" in text
    assert "Morning Run" in text
    assert "Nutrition:" in text


from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_run_briefing_uses_alert_flow_when_env_set(monkeypatch):
    monkeypatch.setenv("BRIEFING_MODE", "alerts")
    monkeypatch.setenv("TELEGRAM_BOT_TOKEN", "t")
    monkeypatch.setenv("TELEGRAM_CHAT_ID", "c")

    fake_metrics = {
        "date": "2026-04-18",
        "sleep": {"duration_seconds": 25200, "deep_sleep_seconds": 5400, "hrv": 54},
        "calendar": None,
    }
    with patch("orchestrator.app.briefing.get_yesterday_metrics",
               AsyncMock(return_value=fake_metrics)), \
         patch("orchestrator.app.briefing.call_agents_for_briefing",
               AsyncMock(return_value={})), \
         patch("orchestrator.app.briefing.send_telegram_message",
               AsyncMock()) as send, \
         patch("orchestrator.app.briefing._get_registry_for_alerts",
               AsyncMock(return_value=None)):
        from orchestrator.app.briefing import run_briefing
        result = await run_briefing(agents={}, use_today=False)

    assert result["status"] == "sent"
    sent_text = send.await_args.args[2]
    assert "Brief —" in sent_text
    assert "Sleep:" in sent_text
