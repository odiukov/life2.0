import pytest
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

from a2a.types import Message, Part, Role, TextPart, TaskState


class _Ctx:
    def __init__(self, text: str, skill: str | None = None):
        self.task_id = "t1"
        self.context_id = "c1"
        self.message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id="m1",
            metadata={"skillId": skill} if skill else None,
        )


class _Queue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, evt):
        self.events.append(evt)


@pytest.mark.asyncio
async def test_executor_runs_get_latest_body_skill():
    from agents.body.app.executor import BodyAgentExecutor

    fake_llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="Weight: 79.6 kg")))

    with patch("agents.body.app.executor._get_llm", return_value=fake_llm), \
         patch("agents.body.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.body.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.body.app.prompt.fetch_body_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.fetch_recent_logs", new=AsyncMock(return_value=[])), \
         patch("agents.body.app.prompt.search_memories", new=AsyncMock(return_value=[])):
        ctx = _Ctx("сколько я вешу", skill="get_latest_body")
        q = _Queue()
        await BodyAgentExecutor().execute(ctx, q)

    states = [getattr(e, "status", None) and e.status.state for e in q.events if hasattr(e, "status")]
    assert TaskState.completed in states


@pytest.mark.asyncio
async def test_executor_fails_gracefully_on_unknown_skill():
    from agents.body.app.executor import BodyAgentExecutor

    fake_llm = SimpleNamespace(ainvoke=AsyncMock(return_value=SimpleNamespace(content="garbage")))
    with patch("agents.body.app.executor._get_llm", return_value=fake_llm):
        ctx = _Ctx("??? nonsense ???", skill=None)
        q = _Queue()
        await BodyAgentExecutor().execute(ctx, q)

    failed_states = [
        e.status.state for e in q.events
        if hasattr(e, "status") and e.status.state == TaskState.failed
    ]
    assert failed_states, "expected failed status when skill cannot be inferred"
