import json
from unittest.mock import AsyncMock, patch
from uuid import uuid4

import pytest

pytestmark = pytest.mark.asyncio

from a2a.types import Message, Part, Role, TextPart


class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, evt):
        self.events.append(evt)


class _FakeContext:
    def __init__(self, text: str, skill_id: str | None = None, params: dict | None = None):
        meta: dict = {}
        if skill_id:
            meta["skillId"] = skill_id
        if params:
            meta["params"] = params
        self.message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id=str(uuid4()),
            metadata=meta or None,
        )
        self.task_id = str(uuid4())
        self.context_id = str(uuid4())


async def test_define_happy_path_creates_row():
    from agents.medication.app.executor import MedicationAgentExecutor

    fake_llm_json = (
        '{"name": "magnesium", "dose": "200mg", "schedule": "daily 21:00", "notes": null}'
    )
    with patch("agents.medication.app.executor._get_llm") as get_llm, \
         patch("agents.medication.app.executor.registry.create", AsyncMock(return_value="uuid-abc")), \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(return_value=type("R", (), {"content": fake_llm_json})())
        get_llm.return_value = llm

        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("магний 200мг каждый вечер", skill_id="define_medication")
        await ex.execute(ctx, q)

    texts = []
    for evt in q.events:
        for art in getattr(evt, "artifact", None) and [evt.artifact] or []:
            for p in art.parts or []:
                root = getattr(p, "root", p)
                if getattr(root, "text", None):
                    texts.append(root.text)
    assert any("tracking 'magnesium'" in t for t in texts)


async def test_define_invalid_llm_response():
    from agents.medication.app.executor import MedicationAgentExecutor

    with patch("agents.medication.app.executor._get_llm") as get_llm, \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(return_value=type("R", (), {"content": "not json"})())
        get_llm.return_value = llm

        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("garbage", skill_id="define_medication")
        await ex.execute(ctx, q)

    texts = [
        getattr(getattr(p, "root", p), "text", None)
        for evt in q.events
        for art in (getattr(evt, "artifact", None) and [evt.artifact] or [])
        for p in (art.parts or [])
    ]
    assert any("couldn't parse" in (t or "") for t in texts)
