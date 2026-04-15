"""sleep executor emits a log_entry artifact only for log_sleep skill."""
from __future__ import annotations

import asyncio
from datetime import datetime, timezone
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


def _artifact_events(queue: _FakeEventQueue):
    return [e for e in queue.events if getattr(e, "artifact", None) is not None]


@pytest.mark.asyncio
@patch("agents.sleep.app.executor.SKILL_PROMPTS", {"log_sleep": AsyncMock(return_value="prompt"), "analyze_sleep": AsyncMock(return_value="prompt")})
@patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.sleep.app.executor._LLM")
async def test_log_sleep_emits_log_entry_artifact(mock_llm):
    from agents.sleep.app.executor import SleepAgentExecutor

    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok logged"))
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

    # Ordering: log_entry must precede analysis in the event stream.
    art_events = _artifact_events(queue)
    art_names = [e.artifact.name for e in art_events]
    assert art_names.index("log_entry") < art_names.index("analysis")

    # Flag check: log_entry is an append chunk; analysis is the final chunk.
    log_evt = next(e for e in art_events if e.artifact.name == "log_entry")
    analysis_evt = next(e for e in art_events if e.artifact.name == "analysis")
    assert log_evt.append is False
    assert log_evt.last_chunk is True
    assert analysis_evt.append is False
    assert analysis_evt.last_chunk is True

    # Timestamp is a parseable tz-aware ISO-8601 UTC string.
    ts = datetime.fromisoformat(data_part.data["timestamp"])
    assert ts.tzinfo is not None
    assert ts.utcoffset().total_seconds() == 0


@pytest.mark.asyncio
@patch("agents.sleep.app.executor.SKILL_PROMPTS", {"log_sleep": AsyncMock(return_value="prompt"), "analyze_sleep": AsyncMock(return_value="prompt")})
@patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.sleep.app.executor._LLM")
async def test_analyze_sleep_does_not_emit_log_entry(mock_llm):
    from agents.sleep.app.executor import SleepAgentExecutor

    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="analysis text"))
    queue = _FakeEventQueue()
    await SleepAgentExecutor().execute(_ctx("how did I sleep this week?", "analyze_sleep"), queue)
    arts = _collected_artifacts(queue)
    names = [a.name for a in arts]
    assert "log_entry" not in names
    assert "analysis" in names


@pytest.mark.asyncio
@patch("agents.sleep.app.executor.SKILL_PROMPTS", {"log_sleep": AsyncMock(return_value="prompt"), "analyze_sleep": AsyncMock(return_value="prompt")})
@patch("agents.sleep.app.executor.insert_task_record", new=AsyncMock())
@patch("agents.sleep.app.executor.upsert_memory", new=AsyncMock())
@patch("agents.sleep.app.executor.fetch_peer_artifacts", new=AsyncMock(return_value={}))
@patch("agents.sleep.app.executor._LLM")
async def test_log_sleep_clips_long_summary(mock_llm):
    from agents.sleep.app.executor import SleepAgentExecutor, _LOG_ENTRY_SUMMARY_MAX

    mock_llm.ainvoke = AsyncMock(return_value=MagicMock(content="ok logged"))
    queue = _FakeEventQueue()
    long_msg = "a" * 250
    await SleepAgentExecutor().execute(_ctx(long_msg, "log_sleep"), queue)
    arts = _collected_artifacts(queue)
    log_art = next(a for a in arts if a.name == "log_entry")
    summary = log_art.parts[0].root.data["summary"]
    assert len(summary) == _LOG_ENTRY_SUMMARY_MAX
    assert summary.endswith("…")
