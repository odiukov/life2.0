import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from a2a.types import Message, Part, Role, TextPart, TaskState


class _Ctx:
    def __init__(self, text: str, skill: str | None = None, params: dict | None = None):
        self.task_id = "t1"
        self.context_id = "c1"
        meta: dict = {}
        if skill:
            meta["skillId"] = skill
        if params is not None:
            meta["params"] = params
        self.message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id="m1",
            metadata=meta or None,
        )


class _Queue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, evt):
        self.events.append(evt)


def _artifact_names(events):
    names = []
    for e in events:
        art = getattr(e, "artifact", None)
        if art is not None:
            names.append(art.name)
    return names


def _fake_llm(content: str):
    return SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content=content)))


@pytest.mark.asyncio
async def test_log_mood_parses_json_and_persists_row():
    from agents.mood.app.executor import MoodAgentExecutor

    llm_json = '{"mood_score":6,"energy":5,"stress":7,"valence":"neu","tags":["anxiety","tired"],"summary":"устал и тревожно"}'
    captured = {}

    async def fake_insert_log(agent, type_, data, source="manual"):
        captured["agent"] = agent
        captured["type"] = type_
        captured["data"] = data
        captured["source"] = source

    with patch("agents.mood.app.executor._get_llm", return_value=_fake_llm(llm_json)), \
         patch("agents.mood.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.mood.app.executor.insert_log", new=fake_insert_log), \
         patch("agents.mood.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.mood.app.prompt.fetch_mood_logs", new=AsyncMock(return_value=[])), \
         patch("agents.mood.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        q = _Queue()
        await MoodAgentExecutor().execute(_Ctx("устал и тревожно", skill="log_mood"), q)

    assert captured["type"] == "mood"
    assert captured["data"]["mood_score"] == 6
    assert captured["data"]["stress"] == 7
    assert captured["data"]["raw_text"] == "устал и тревожно"
    assert captured["data"]["source_skill"] == "log_mood"
    # must emit both a log_entry DataPart and a text artifact
    assert "log_entry" in _artifact_names(q.events)


@pytest.mark.asyncio
async def test_log_mood_fallback_when_json_invalid():
    from agents.mood.app.executor import MoodAgentExecutor

    captured = {}

    async def fake_insert_log(agent, type_, data, source="manual"):
        captured["data"] = data

    with patch("agents.mood.app.executor._get_llm", return_value=_fake_llm("not json at all")), \
         patch("agents.mood.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.mood.app.executor.insert_log", new=fake_insert_log), \
         patch("agents.mood.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.mood.app.prompt.fetch_mood_logs", new=AsyncMock(return_value=[])), \
         patch("agents.mood.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        q = _Queue()
        await MoodAgentExecutor().execute(_Ctx("hi", skill="log_mood"), q)

    assert captured["data"]["source_skill"] == "log_mood_fallback"
    assert captured["data"]["mood_score"] is None
    assert captured["data"]["raw_text"] == "hi"


@pytest.mark.asyncio
async def test_analyze_mood_completes_without_logging():
    from agents.mood.app.executor import MoodAgentExecutor

    with patch("agents.mood.app.executor._get_llm", return_value=_fake_llm("Trend: stable.")), \
         patch("agents.mood.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.mood.app.executor.insert_log", new=AsyncMock()) as il, \
         patch("agents.mood.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.mood.app.prompt.fetch_mood_logs", new=AsyncMock(return_value=[])), \
         patch("agents.mood.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        q = _Queue()
        await MoodAgentExecutor().execute(_Ctx("trend?", skill="analyze_mood"), q)

    il.assert_not_called()
    states = [e.status.state for e in q.events if hasattr(e, "status")]
    assert TaskState.completed in states


@pytest.mark.asyncio
async def test_unknown_skill_fails_cleanly():
    from agents.mood.app.executor import MoodAgentExecutor

    with patch("agents.mood.app.executor._get_llm", return_value=_fake_llm("??")):
        q = _Queue()
        await MoodAgentExecutor().execute(_Ctx("???"), q)

    failed = [
        e for e in q.events
        if hasattr(e, "status") and e.status.state == TaskState.failed
    ]
    assert failed
