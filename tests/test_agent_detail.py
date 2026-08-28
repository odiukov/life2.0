"""Tests for agent_detail builders and insight formulas.

DB-dependent tests are skipped without POSTGRES_DSN.
"""
import os
import pytest

# ── Insight formula tests (pure, no DB) ─────────────────────────────────────

from orchestrator.app.agent_detail import (
    _sleep_insight,
    _workout_insight,
    _nutrition_insight,
    _mood_insight,
    _habits_insight,
    _recovery_insight,
    _medication_insight,
    _finance_insight,
    VALID_AGENT_IDS,
)


def _hist(values: list[float]) -> list[dict]:
    """Build a minimal history list from a list of values."""
    from datetime import date, timedelta
    today = date.today()
    return [
        {"date": (today - timedelta(days=len(values) - 1 - i)).isoformat(),
         "value": v, "label": str(v)}
        for i, v in enumerate(values)
    ]


# Sleep

def test_sleep_insight_above_average():
    hist = _hist([6.0, 6.5, 7.0, 6.0, 7.5, 7.0, 8.0])
    insight = _sleep_insight(hist, {})
    assert "above" in insight.lower() or "average" in insight.lower()


def test_sleep_insight_empty_when_insufficient():
    hist = _hist([0.0, 0.0])
    assert _sleep_insight(hist, {}) == ""


# Workout

def test_workout_insight_counts_workouts():
    # 3 non-zero days this week
    hist = _hist([5.0, 0.0, 4.0, 0.0, 6.0, 0.0, 0.0])
    insight = _workout_insight(hist, {})
    assert "3" in insight


def test_workout_insight_empty_when_no_data():
    hist = _hist([0.0] * 7)
    assert _workout_insight(hist, {}) == ""


# Nutrition

def test_nutrition_insight_protein_deficit():
    hist = _hist([2000.0] * 7)
    metrics = {"protein_g": 40, "protein_goal_g": 120}
    insight = _nutrition_insight(hist, metrics)
    assert "protein" in insight.lower()


def test_nutrition_day_bounds_use_utc_day():
    from datetime import datetime, timezone
    from orchestrator.app.agent_detail import _nutrition_day_bounds

    start, end = _nutrition_day_bounds(datetime(2026, 5, 5, 21, 20, tzinfo=timezone.utc))

    assert start.isoformat() == "2026-05-05T00:00:00+00:00"
    assert end.isoformat() == "2026-05-06T00:00:00+00:00"


# Mood

def test_mood_insight_upward_trend():
    hist = _hist([5.0, 5.0, 5.0, 6.0, 7.0, 7.5, 8.0])
    insight = _mood_insight(hist, {})
    assert "up" in insight.lower() or "trending" in insight.lower() or "improving" in insight.lower()


def test_mood_insight_empty_when_insufficient():
    assert _mood_insight(_hist([0.0] * 3), {}) == ""


# Habits

def test_habits_insight_streak():
    metrics = {"streak": 7, "completion_7d": 0.85, "missed_names": []}
    insight = _habits_insight(_hist([1.0] * 7), metrics)
    assert "7" in insight


# Recovery

def test_recovery_insight_recovered():
    metrics = {"bucket": "recovered", "hrv": 65, "rhr": 52}
    insight = _recovery_insight(_hist([65.0] * 7), metrics)
    assert "ready" in insight.lower() or "recovered" in insight.lower()


def test_recovery_insight_depleted():
    metrics = {"bucket": "depleted", "hrv": 40, "rhr": 62}
    insight = _recovery_insight(_hist([40.0] * 7), metrics)
    assert "rest" in insight.lower() or "depleted" in insight.lower()


def test_recovery_insight_empty_when_unknown():
    metrics = {"bucket": "unknown"}
    assert _recovery_insight(_hist([0.0] * 7), metrics) == ""


# Medication

def test_medication_insight_missed():
    hist = _hist([1, 1, 0, 1, 0, 1, 1])  # 2 misses
    metrics = {"adherence_7d": 0.71, "missed_names": ["magnesium", "vitamin D"]}
    insight = _medication_insight(hist, metrics)
    assert "magnesium" in insight or "2" in insight


def test_medication_insight_perfect():
    hist = _hist([1.0] * 7)
    metrics = {"adherence_7d": 1.0, "missed_names": []}
    insight = _medication_insight(hist, metrics)
    assert insight  # some positive message


# Finance

def test_finance_insight_spending_up():
    # last 7 days: first 4 avg $50/day, last 3 avg $80/day
    hist = _hist([50.0, 50.0, 50.0, 50.0, 80.0, 80.0, 80.0])
    metrics = {"top_category": "food"}
    insight = _finance_insight(hist, metrics)
    assert "%" in insight or "above" in insight.lower() or "up" in insight.lower()


# ── Endpoint tests ────────────────────────────────────────────────────────────
from unittest.mock import AsyncMock, patch
from uuid import UUID


TEST_USER_ID = UUID("00000000-0000-0000-0000-000000000001")


@pytest.fixture
def mock_detail_response():
    return {
        "agent": "sleep",
        "insight": "Above average last night.",
        "metrics": {"deep_hours": 1.5, "hrv": 60},
        "history": [
            {"date": "2026-04-18", "value": 7.0, "label": "7h"},
            {"date": "2026-04-19", "value": 7.5, "label": "7h 30m"},
        ],
    }


def test_agent_detail_endpoint_returns_200(mock_detail_response):
    from fastapi.testclient import TestClient
    from orchestrator.app.main import app
    from orchestrator.app.auth import current_user

    async def override_current_user():
        return TEST_USER_ID

    app.dependency_overrides[current_user] = override_current_user
    try:
        with patch(
            "orchestrator.app.agent_detail.get_agent_detail",
            new=AsyncMock(return_value=mock_detail_response),
        ):
            client = TestClient(app)
            resp = client.get("/agents/sleep/detail")
        assert resp.status_code == 200
        body = resp.json()
        assert body["agent"] == "sleep"
        assert "insight" in body
        assert "history" in body
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_agent_detail_endpoint_returns_404_for_unknown():
    from fastapi.testclient import TestClient
    from orchestrator.app.main import app
    from orchestrator.app.auth import current_user

    async def override_current_user():
        return TEST_USER_ID

    app.dependency_overrides[current_user] = override_current_user
    try:
        client = TestClient(app)
        resp = client.get("/agents/unknown_agent/detail")
        assert resp.status_code == 404
    finally:
        app.dependency_overrides.pop(current_user, None)


def test_calendar_detail_is_registered():
    assert "calendar" in VALID_AGENT_IDS


@pytest.mark.asyncio
async def test_calendar_detail_returns_real_events_from_google():
    from orchestrator.app.agent_detail import _calendar_detail

    items = [
        {
            "summary": "Design review",
            "start": {"dateTime": "2026-05-05T10:30:00+03:00"},
            "end": {"dateTime": "2026-05-05T11:30:00+03:00"},
        },
        {
            "summary": "Lunch",
            "start": {"dateTime": "2026-05-05T12:00:00+03:00"},
            "end": {"dateTime": "2026-05-05T12:45:00+03:00"},
        },
    ]

    with patch(
        "orchestrator.app.google_calendar_api.list_events",
        new=AsyncMock(return_value=items),
    ):
        detail = await _calendar_detail(TEST_USER_ID)

    assert detail["agent"] == "calendar"
    assert detail["metrics"]["events_count"] == 2
    assert detail["metrics"]["busy_minutes"] == 105
    assert detail["metrics"]["events"][0]["name"] == "Design review"


@pytest.mark.asyncio
async def test_nutrition_detail_returns_today_meals():
    from orchestrator.app.agent_detail import _nutrition_detail

    class Pool:
        async def fetchrow(self, query, *args):
            return {"protein_g": 55, "carbs_g": 120, "fat_g": 42, "kcal": 1100}

        async def fetch(self, query, *args):
            return [
                {
                    "recorded_at": "2026-05-05T08:00:00+00:00",
                    "data": {
                        "meal_type": "breakfast",
                        "items": [
                            {"name": "Greek yogurt", "kcal": 180},
                            {"name": "Berries", "kcal": 60},
                        ],
                        "totals": {"kcal": 240},
                    },
                },
                {
                    "recorded_at": "2026-05-05T12:00:00+00:00",
                    "data": {
                        "meal_type": "lunch",
                        "items": [{"name": "Salmon bowl", "kcal": 720}],
                        "totals": {"kcal": 720},
                    },
                },
            ]

    with patch("orchestrator.app.db.fetch_nutrition_history", new=AsyncMock(return_value=[])), \
         patch("orchestrator.app.db.get_pool", new=AsyncMock(return_value=Pool())), \
         patch("orchestrator.app.db.get_body_profile", new=AsyncMock(return_value={})):
        detail = await _nutrition_detail(TEST_USER_ID)

    assert detail["meals"] == [
        {
            "meal_type": "breakfast",
            "label": "Breakfast",
            "items": ["Greek yogurt", "Berries"],
            "kcal": 240,
            "recorded_at": "2026-05-05T08:00:00+00:00",
        },
        {
            "meal_type": "lunch",
            "label": "Lunch",
            "items": ["Salmon bowl"],
            "kcal": 720,
            "recorded_at": "2026-05-05T12:00:00+00:00",
        },
    ]
