# New contract: body prompt no longer does direct cross-domain reads via
# fetch_recent_logs. Cross-domain context (nutrition / workout / recovery)
# arrives as peer_artifacts threaded by the executor. See spec §5 + §10.
import pytest
from uuid import UUID
from unittest.mock import AsyncMock, patch
from datetime import datetime, timezone

USER = UUID("00000000-0000-0000-0000-000000000001")
PARAMS = {"user_id": str(USER)}


@pytest.fixture
def body_row():
    return {
        "type": "body_composition",
        "source": "vihealth",
        "recorded_at": datetime(2026, 4, 14, 9, 37, 16, tzinfo=timezone.utc),
        "data": {
            "weight_kg": 79.6, "body_fat_pct": 26.5, "muscle_kg": 54.6,
            "skeletal_muscle_kg": 33.1, "bmr_kcal": 1633,
            "visceral_fat_grade": 8, "body_age": 32, "body_score": 73,
        },
    }


@pytest.mark.asyncio
async def test_get_latest_body_includes_weight(body_row):
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[body_row])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        prompt = await build_body_prompt("get_latest_body", PARAMS)

    assert "79.6" in prompt
    assert "26.5" in prompt
    assert "get_latest_body" in prompt


@pytest.mark.asyncio
async def test_analyze_body_trend_renders_peer_artifacts(body_row):
    """Cross-domain context now flows through peer_artifacts, not direct DB reads."""
    peer_artifacts = {
        "nutrition": "Avg 2100 kcal/day, protein 130g.",
        "workout": "5 sessions last week, mostly strength.",
    }
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[body_row])) as mb, \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        prompt = await build_body_prompt(
            "analyze_body_trend", PARAMS, peer_artifacts=peer_artifacts,
        )

    assert mb.called
    assert "## Peer context" in prompt
    assert "### nutrition" in prompt
    assert "### workout" in prompt
    assert "2100 kcal" in prompt
    assert "5 sessions" in prompt


@pytest.mark.asyncio
async def test_body_prompt_handles_empty_data():
    with patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        from agents.body.app.prompt import build_body_prompt
        prompt = await build_body_prompt("get_latest_body", PARAMS)

    assert "No body composition" in prompt or "no body" in prompt.lower()
