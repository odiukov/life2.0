import json
from unittest.mock import AsyncMock, patch
from uuid import UUID, uuid4

import pytest

pytestmark = pytest.mark.asyncio

from a2a.types import Message, Part, Role, TextPart


USER = UUID("00000000-0000-0000-0000-000000000001")


def _patch_owner():
    return patch(
        "agents.medication.app.executor.user_id_from_message",
        new=AsyncMock(return_value=USER),
    )


class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, evt):
        self.events.append(evt)


class _FakeContext:
    def __init__(self, text, skill_id, params=None, user_id=None):
        meta = {"skillId": skill_id}
        if params:
            meta["params"] = params
        if user_id:
            meta["user_id"] = str(user_id)
        self.message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=text))],
            message_id=str(uuid4()),
            metadata=meta,
        )
        self.task_id = str(uuid4())
        self.context_id = str(uuid4())


def _texts(q):
    return [
        getattr(getattr(p, "root", p), "text", None)
        for evt in q.events
        for art in (getattr(evt, "artifact", None) and [evt.artifact] or [])
        for p in (art.parts or [])
    ]


async def test_log_medication_resolves_name_and_inserts_log():
    from agents.medication.app.executor import MedicationAgentExecutor

    fake_med = {"id": "uuid-mag", "name": "magnesium", "dose": "200mg",
                "schedule": "daily 21:00", "notes": None, "created_at": None}

    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.find_by_name",
               AsyncMock(return_value=fake_med)), \
         patch("agents.medication.app.executor.insert_log", AsyncMock()) as insert, \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("/med magnesium", "log_medication", {"name": "magnesium"})
        await ex.execute(ctx, q)

    insert.assert_awaited_once()
    # New signature: insert_log(user_id, agent=..., type_=..., data=..., source=...)
    assert insert.await_args.args[0] == USER
    kwargs = insert.await_args.kwargs
    assert kwargs["agent"] == "medication"
    assert kwargs["type_"] == "medication_taken"
    assert kwargs["data"]["name"] == "magnesium"
    assert any("taken 'magnesium'" in (t or "") for t in _texts(q))


async def test_log_medication_unknown_name_hint():
    from agents.medication.app.executor import MedicationAgentExecutor

    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.find_by_name",
               AsyncMock(return_value=None)), \
         patch("agents.medication.app.executor.insert_log", AsyncMock()), \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("random", "log_medication", {"name": "unknown"})
        await ex.execute(ctx, q)

    assert any("not found" in (t or "") for t in _texts(q))


async def test_list_active_formats_deterministic_summary():
    from agents.medication.app.executor import MedicationAgentExecutor
    meds = [
        {"id": "a", "name": "magnesium", "dose": "200mg", "schedule": "daily 21:00", "notes": None, "created_at": None},
        {"id": "b", "name": "vitamin-d", "dose": "2000IU", "schedule": "daily morning", "notes": None, "created_at": None},
    ]
    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.list_active",
               AsyncMock(return_value=meds)), \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("", "list_active")
        await ex.execute(ctx, q)

    joined = "\n".join(t for t in _texts(q) if t)
    assert "magnesium" in joined
    assert "vitamin-d" in joined


async def test_list_active_empty():
    from agents.medication.app.executor import MedicationAgentExecutor
    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.list_active",
               AsyncMock(return_value=[])), \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("", "list_active")
        await ex.execute(ctx, q)
    assert any("no active medications" in (t or "") for t in _texts(q))


async def test_analyze_adherence_runs_llm_with_real_data():
    from agents.medication.app.executor import MedicationAgentExecutor
    meds = [{"id": "a", "name": "magnesium", "dose": None,
             "schedule": "daily 21:00", "notes": None, "created_at": None}]
    logs = [{"data": {"name": "magnesium"}, "recorded_at": None}] * 10  # 10 takes in 14 days

    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.list_active",
               AsyncMock(return_value=meds)), \
         patch("agents.medication.app.executor.fetch_medication_logs",
               AsyncMock(return_value=logs)), \
         patch("agents.medication.app.executor._get_llm") as get_llm, \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        llm = AsyncMock()
        llm.ainvoke = AsyncMock(return_value=type("R", (), {"content": "Good adherence."})())
        get_llm.return_value = llm

        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("how's my adherence", "analyze_adherence")
        await ex.execute(ctx, q)

    assert any("Good adherence" in (t or "") for t in _texts(q))


async def test_archive_medication_soft_deletes():
    from agents.medication.app.executor import MedicationAgentExecutor
    fake_med = {"id": "uuid-zz", "name": "zinc", "dose": "15mg",
                "schedule": "daily", "notes": None, "created_at": None}

    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.find_by_name",
               AsyncMock(return_value=fake_med)), \
         patch("agents.medication.app.executor.registry.archive",
               AsyncMock(return_value=True)) as arch, \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("stop zinc", "archive_medication", {"name": "zinc"})
        await ex.execute(ctx, q)

    arch.assert_awaited_once_with(USER, "uuid-zz")
    assert any("archived" in (t or "") for t in _texts(q))


async def test_archive_medication_unknown_name():
    from agents.medication.app.executor import MedicationAgentExecutor

    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.find_by_name",
               AsyncMock(return_value=None)), \
         patch("agents.medication.app.executor.insert_task_record", AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory", AsyncMock()):
        ex = MedicationAgentExecutor()
        q = _FakeQueue()
        ctx = _FakeContext("stop xxx", "archive_medication", {"name": "xxx"})
        await ex.execute(ctx, q)
    assert any("not found" in (t or "") for t in _texts(q))


async def test_log_medication_uses_user_id_from_message_not_legacy_owner():
    """Regression: medication executor resolves uid from the incoming
    Message's metadata via user_id_from_message().
    Multi-tenant safety after multi-user auth shipped 2026-04-22."""
    from agents.medication.app.executor import MedicationAgentExecutor

    other_user = UUID("00000000-0000-0000-0000-000000000099")
    fake_med = {"id": "uuid-mag", "name": "magnesium", "dose": "200mg",
                "schedule": "daily 21:00", "notes": None, "created_at": None}

    with patch(
            "agents.medication.app.executor.user_id_from_message",
            new=AsyncMock(return_value=other_user)
        ), \
        patch("agents.medication.app.executor.registry.find_by_name",
              new=AsyncMock(return_value=fake_med)), \
        patch("agents.medication.app.executor.insert_log",
              new=AsyncMock()) as mock_insert, \
        patch("agents.medication.app.executor.insert_task_record",
              new=AsyncMock()), \
        patch("agents.medication.app.executor.upsert_memory",
              new=AsyncMock()):

        ctx = _FakeContext("magnesium", "log_medication", {"name": "magnesium"})
        q = _FakeQueue()
        await MedicationAgentExecutor().execute(ctx, q)

    mock_insert.assert_awaited_once()
    # insert_log signature: insert_log(user_id, agent=..., type_=..., data=..., source=...)
    assert mock_insert.await_args.args[0] == other_user, (
        "expected uid from message metadata, got something else"
    )


async def test_log_medication_emits_log_entry_artifact():
    """log_medication must emit a log_entry DataPart so the chat UI shows
    a toast card."""
    from agents.medication.app.executor import MedicationAgentExecutor
    from a2a.types import DataPart

    fake_med = {"id": "uuid-mag", "name": "magnesium", "dose": "200mg",
                "schedule": "daily 21:00", "notes": None, "created_at": None}

    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.find_by_name",
               new=AsyncMock(return_value=fake_med)), \
         patch("agents.medication.app.executor.insert_log",
               new=AsyncMock()), \
         patch("agents.medication.app.executor.insert_task_record",
               new=AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory",
               new=AsyncMock()):
        ctx = _FakeContext("magnesium", "log_medication", {"name": "magnesium"})
        q = _FakeQueue()
        await MedicationAgentExecutor().execute(ctx, q)

    log_entry_data = None
    for evt in q.events:
        art = getattr(evt, "artifact", None)
        if art is None or art.name != "log_entry":
            continue
        root = getattr(art.parts[0], "root", art.parts[0])
        if isinstance(root, DataPart):
            log_entry_data = root.data
    assert log_entry_data is not None
    assert "summary" in log_entry_data
    assert "timestamp" in log_entry_data


async def test_archive_medication_emits_log_entry_artifact():
    from agents.medication.app.executor import MedicationAgentExecutor

    fake_med = {"id": "uuid-mag", "name": "magnesium", "dose": "200mg",
                "schedule": "daily 21:00", "notes": None, "created_at": None}

    with _patch_owner(), \
         patch("agents.medication.app.executor.registry.find_by_name",
               new=AsyncMock(return_value=fake_med)), \
         patch("agents.medication.app.executor.registry.archive",
               new=AsyncMock(return_value=True)), \
         patch("agents.medication.app.executor.insert_task_record",
               new=AsyncMock()), \
         patch("agents.medication.app.executor.upsert_memory",
               new=AsyncMock()):
        ctx = _FakeContext("magnesium", "archive_medication",
                          {"name": "magnesium"})
        q = _FakeQueue()
        await MedicationAgentExecutor().execute(ctx, q)

    found = any(
        getattr(getattr(evt, "artifact", None), "name", None) == "log_entry"
        for evt in q.events
    )
    assert found, "archive_medication must emit a log_entry artifact"
