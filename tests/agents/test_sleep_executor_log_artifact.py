"""sleep executor emits a log_entry artifact only for log_sleep skill."""
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
@patch("agents.sleep.app.executor.SKILL_PROMPTS", {"log_sleep": AsyncMock(return_value="prompt"), "analyze_sleep": AsyncMock(return_value="prompt")})
@patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.sleep.app.executor.run_claude", return_value="ok logged")
async def test_log_sleep_emits_log_entry_artifact(run_claude_mock):
    from agents.sleep.app.executor import SleepAgentExecutor

    queue = _FakeEventQueue()
    await SleepAgentExecutor().execute(_ctx("slept 8h yesterday", "log_sleep"), queue)
    arts = _collected_artifacts(queue)
    names = [a.name for a in arts]
    assert "log_entry" in names
    log_art = next(a for a in arts if a.name == "log_entry")
    data_part = log_art.parts[0].root
    assert isinstance(data_part, DataPart)
    assert data_part.data["summary"].startswith("slept 8h")
    assert "timestamp" in data_part.data


@pytest.mark.asyncio
@patch("agents.sleep.app.executor.SKILL_PROMPTS", {"log_sleep": AsyncMock(return_value="prompt"), "analyze_sleep": AsyncMock(return_value="prompt")})
@patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.sleep.app.executor.run_claude", return_value="analysis text")
async def test_analyze_sleep_does_not_emit_log_entry(run_claude_mock):
    from agents.sleep.app.executor import SleepAgentExecutor

    queue = _FakeEventQueue()
    await SleepAgentExecutor().execute(_ctx("how did I sleep this week?", "analyze_sleep"), queue)
    arts = _collected_artifacts(queue)
    names = [a.name for a in arts]
    assert "log_entry" not in names
    assert "analysis" in names
