"""workout executor emits a log_entry artifact only for log_workout skill."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from a2a.types import Artifact, DataPart, Message, Part, Role, TextPart


class _FakeEventQueue:
    def __init__(self) -> None:
        self.events: list = []

    async def enqueue_event(self, evt):  # noqa: D401
        self.events.append(evt)


def _ctx(message_text: str, skill_id: str):
    msg = Message(
        role=Role.user,
        parts=[Part(root=TextPart(text=message_text))],
        message_id="m1",
        metadata={"skillId": skill_id},
    )
    ctx = MagicMock()
    ctx.message = msg
    ctx.task_id = "t1"
    ctx.context_id = "c1"
    ctx.current_task = None
    return ctx


def _collected_artifacts(queue: _FakeEventQueue) -> list[Artifact]:
    out = []
    for e in queue.events:
        art = getattr(e, "artifact", None)
        if art is not None:
            out.append(art)
    return out


@pytest.mark.asyncio
@patch("agents.workout.app.executor.SKILL_PROMPTS", {"log_workout": AsyncMock(return_value="prompt"), "analyze_workout": AsyncMock(return_value="prompt")})
@patch("agents.workout.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.workout.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.workout.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.workout.app.executor.run_claude", return_value="ok logged")
async def test_log_workout_emits_log_entry_artifact(run_claude_mock):
    from agents.workout.app.executor import WorkoutAgentExecutor

    queue = _FakeEventQueue()
    await WorkoutAgentExecutor().execute(_ctx("30 min run today", "log_workout"), queue)
    arts = _collected_artifacts(queue)
    names = [a.name for a in arts]
    assert "log_entry" in names
    log_art = next(a for a in arts if a.name == "log_entry")
    data_part = log_art.parts[0].root
    assert isinstance(data_part, DataPart)
    assert data_part.data["summary"].startswith("30 min run")
    assert "timestamp" in data_part.data


@pytest.mark.asyncio
@patch("agents.workout.app.executor.SKILL_PROMPTS", {"log_workout": AsyncMock(return_value="prompt"), "analyze_workout": AsyncMock(return_value="prompt")})
@patch("agents.workout.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.workout.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.workout.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.workout.app.executor.run_claude", return_value="analysis text")
async def test_analyze_workout_does_not_emit_log_entry(run_claude_mock):
    from agents.workout.app.executor import WorkoutAgentExecutor

    queue = _FakeEventQueue()
    await WorkoutAgentExecutor().execute(_ctx("how hard was last week?", "analyze_workout"), queue)
    arts = _collected_artifacts(queue)
    names = [a.name for a in arts]
    assert "log_entry" not in names
    assert "analysis" in names
