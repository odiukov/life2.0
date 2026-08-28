"""Tests for recovery prompt builders. Mocks fetch_recovery_metrics."""
import pytest
from uuid import UUID
from datetime import date
from unittest.mock import AsyncMock, patch

USER = UUID("00000000-0000-0000-0000-000000000001")


_FAKE_METRICS = {
    "2026-04-17": {"hrv": 45, "rhr": 58, "stress": 34, "bb_min": 25, "bb_max": 85, "sleep_score": 82},
    "2026-04-16": {"hrv": 42, "rhr": 60, "stress": 40, "bb_min": 20, "bb_max": 80, "sleep_score": 78},
    "2026-04-15": {"hrv": 44, "rhr": 59, "stress": 38, "bb_min": 22, "bb_max": 82, "sleep_score": 80},
    "2026-04-14": {"hrv": 43, "rhr": 60, "stress": 42, "bb_min": 18, "bb_max": 79, "sleep_score": 75},
    "2026-04-13": {"hrv": 46, "rhr": 57, "stress": 32, "bb_min": 28, "bb_max": 88, "sleep_score": 85},
    "2026-04-12": {"hrv": 45, "rhr": 58, "stress": 35, "bb_min": 24, "bb_max": 83, "sleep_score": 81},
    "2026-04-11": {"hrv": 44, "rhr": 59, "stress": 36, "bb_min": 23, "bb_max": 81, "sleep_score": 79},
}


@pytest.mark.asyncio
async def test_readiness_prompt_includes_snapshot_and_bucket():
    with patch("agents.recovery.app.prompt.fetch_recovery_metrics",
               new=AsyncMock(return_value=_FAKE_METRICS)):
        from agents.recovery.app.prompt import build_recovery_prompt
        prompt = await build_recovery_prompt("get_readiness", {"user_id": str(USER), "message": "am I recovered"})
    lower = prompt.lower()
    assert any(b in lower for b in ("recovered", "neutral", "depleted", "unknown"))
    for label in ("hrv", "rhr", "stress", "body battery"):
        assert label in lower


@pytest.mark.asyncio
async def test_trend_prompt_includes_7day_history():
    with patch("agents.recovery.app.prompt.fetch_recovery_metrics",
               new=AsyncMock(return_value=_FAKE_METRICS)):
        from agents.recovery.app.prompt import build_recovery_prompt
        prompt = await build_recovery_prompt(
            "analyze_recovery_trend", {"user_id": str(USER), "message": "trend this week"}
        )
    assert prompt.count("2026-04-") >= 5


@pytest.mark.asyncio
async def test_recommendations_prompt_asks_for_2_3_actions():
    with patch("agents.recovery.app.prompt.fetch_recovery_metrics",
               new=AsyncMock(return_value=_FAKE_METRICS)):
        from agents.recovery.app.prompt import build_recovery_prompt
        prompt = await build_recovery_prompt(
            "get_recommendations", {"user_id": str(USER), "message": "what should I do"}
        )
    lower = prompt.lower()
    assert "2" in lower or "3" in lower or "two" in lower or "three" in lower
    assert "actionable" in lower or "action" in lower or "recommend" in lower


@pytest.mark.asyncio
async def test_readiness_prompt_handles_empty_data():
    with patch("agents.recovery.app.prompt.fetch_recovery_metrics",
               new=AsyncMock(return_value={})):
        from agents.recovery.app.prompt import build_recovery_prompt
        prompt = await build_recovery_prompt("get_readiness", {"user_id": str(USER), "message": "am I recovered"})
    lower = prompt.lower()
    assert "not enough" in lower or "no recovery data" in lower or "unknown" in lower
