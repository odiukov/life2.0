from unittest.mock import AsyncMock, patch

import pytest


@pytest.mark.asyncio
async def test_call_agent_with_artifact_includes_focus_sources_when_provided():
    """The A2A Message metadata must carry focus_sources end-to-end."""
    from orchestrator.app.health_agent import _call_agent_with_artifact

    captured: dict = {}

    class FakeClient:
        def send_message(self, msg):
            captured["metadata"] = msg.metadata

            async def _gen():
                if False:
                    yield

            return _gen()

    fake_client = FakeClient()

    with patch("orchestrator.app.health_agent._resolve_url", return_value="http://x"), \
         patch("orchestrator.app.health_agent.get_client",
               new=AsyncMock(return_value=fake_client)):
        await _call_agent_with_artifact(
            agent="workout",
            message="посоветуй тренировку с учётом сна",
            skill="get_workout_recommendations",
            user_id="u1",
            focus_sources=["sleep"],
        )

    assert captured["metadata"]["skillId"] == "get_workout_recommendations"
    assert captured["metadata"]["focus_sources"] == ["sleep"]
    assert captured["metadata"]["user_id"] == "u1"


@pytest.mark.asyncio
async def test_call_agent_with_artifact_omits_focus_sources_when_none():
    """No focus_sources → key absent from metadata (avoids spurious empty list)."""
    from orchestrator.app.health_agent import _call_agent_with_artifact

    captured: dict = {}

    class FakeClient:
        def send_message(self, msg):
            captured["metadata"] = msg.metadata

            async def _gen():
                if False:
                    yield

            return _gen()

    fake_client = FakeClient()
    with patch("orchestrator.app.health_agent._resolve_url", return_value="http://x"), \
         patch("orchestrator.app.health_agent.get_client",
               new=AsyncMock(return_value=fake_client)):
        await _call_agent_with_artifact(
            agent="workout", message="m", skill="analyze_workout", user_id="u1",
        )
    assert "focus_sources" not in captured["metadata"]
