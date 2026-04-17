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
async def test_define_habit_parses_json_and_creates_registry_row():
    from agents.habits.app.executor import HabitsAgentExecutor

    llm_json = (
        '{"name":"meditation","kind":"quantitative","cadence_type":"daily",'
        '"cadence_days":null,"target_value":20,"unit":"min"}'
    )
    captured = {}

    async def fake_create(**kwargs):
        captured.update(kwargs)
        return "fake-uuid-1"

    with patch("agents.habits.app.executor._get_llm", return_value=_fake_llm(llm_json)), \
         patch("agents.habits.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.habits.app.executor.registry.create", new=fake_create), \
         patch("agents.habits.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[])):
        q = _Queue()
        await HabitsAgentExecutor().execute(
            _Ctx("медитация 20 минут каждый день", skill="define_habit"), q,
        )
    assert captured["name"] == "meditation"
    assert captured["kind"] == "quantitative"
    assert captured["cadence_type"] == "daily"
    assert captured["target_value"] == 20
    assert captured["unit"] == "min"


@pytest.mark.asyncio
async def test_define_habit_fallback_on_invalid_json_writes_no_row():
    from agents.habits.app.executor import HabitsAgentExecutor

    called = {"n": 0}

    async def fake_create(**kwargs):
        called["n"] += 1
        return "should-not-be-called"

    with patch("agents.habits.app.executor._get_llm",
               return_value=_fake_llm("i cannot parse this")), \
         patch("agents.habits.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.habits.app.executor.registry.create", new=fake_create), \
         patch("agents.habits.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[])):
        q = _Queue()
        await HabitsAgentExecutor().execute(
            _Ctx("dunno really", skill="define_habit"), q,
        )
    assert called["n"] == 0
    states = [e.status.state for e in q.events if hasattr(e, "status")]
    assert TaskState.completed in states


@pytest.mark.asyncio
async def test_log_habit_check_resolves_name_and_inserts_log():
    from agents.habits.app.executor import HabitsAgentExecutor

    captured = {}

    async def fake_insert_log(agent, type_, data, source="manual"):
        captured["data"] = data
        captured["type"] = type_
        captured["agent"] = agent

    async def fake_find(name):
        return {
            "id": "abc-123", "name": "meditation",
            "kind": "quantitative", "target_value": 20, "unit": "min",
        } if name == "meditation" else None

    with patch("agents.habits.app.executor._get_llm", return_value=_fake_llm("")), \
         patch("agents.habits.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.habits.app.executor.insert_log", new=fake_insert_log), \
         patch("agents.habits.app.executor.registry.find_by_name", new=fake_find), \
         patch("agents.habits.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[])):
        q = _Queue()
        await HabitsAgentExecutor().execute(
            _Ctx(
                "/habit meditation 15min",
                skill="log_habit_check",
                params={"name": "meditation", "value": 15, "unit": "min"},
            ),
            q,
        )
    assert captured["type"] == "habit"
    assert captured["data"]["habit_id"] == "abc-123"
    assert captured["data"]["name"] == "meditation"
    assert captured["data"]["value"] == 15
    assert captured["data"]["unit"] == "min"
    assert captured["data"]["completed"] is True
    assert "log_entry" in _artifact_names(q.events)


@pytest.mark.asyncio
async def test_log_habit_check_unknown_name_does_not_insert():
    from agents.habits.app.executor import HabitsAgentExecutor

    inserts = {"n": 0}

    async def fake_insert_log(*a, **kw):
        inserts["n"] += 1

    async def fake_find(name):
        return None

    with patch("agents.habits.app.executor._get_llm", return_value=_fake_llm("")), \
         patch("agents.habits.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.habits.app.executor.insert_log", new=fake_insert_log), \
         patch("agents.habits.app.executor.registry.find_by_name", new=fake_find), \
         patch("agents.habits.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[])):
        q = _Queue()
        await HabitsAgentExecutor().execute(
            _Ctx("/habit nope", skill="log_habit_check", params={"name": "nope"}), q,
        )
    assert inserts["n"] == 0


@pytest.mark.asyncio
async def test_get_streak_summary_is_deterministic_no_llm():
    from datetime import datetime, timezone, timedelta
    from agents.habits.app.executor import HabitsAgentExecutor

    habits = [
        {"id": "h-1", "name": "meditation", "kind": "quantitative",
         "cadence_type": "daily", "cadence_days": None,
         "target_value": 20, "unit": "min",
         "created_at": datetime(2026, 4, 10, tzinfo=timezone.utc)},
        {"id": "h-2", "name": "cold-shower", "kind": "boolean",
         "cadence_type": "daily", "cadence_days": None,
         "target_value": None, "unit": None,
         "created_at": datetime(2026, 4, 10, tzinfo=timezone.utc)},
    ]
    now = datetime.now(timezone.utc)
    logs = []
    for days_ago in (0, 1, 2):
        logs.append({
            "recorded_at": now - timedelta(days=days_ago),
            "data": {"habit_id": "h-1", "name": "meditation",
                     "completed": True, "value": 25, "unit": "min"},
        })

    llm_mock = _fake_llm("SHOULD-NOT-APPEAR")

    with patch("agents.habits.app.executor._get_llm", return_value=llm_mock), \
         patch("agents.habits.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.habits.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.habits.app.executor.registry.list_active",
               new=AsyncMock(return_value=habits)), \
         patch("agents.habits.app.executor.fetch_habit_logs",
               new=AsyncMock(return_value=logs)), \
         patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=habits)), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=logs)):
        q = _Queue()
        await HabitsAgentExecutor().execute(
            _Ctx("/habits", skill="get_streak_summary"), q,
        )

    llm_mock.ainvoke.assert_not_called()
    text_artifacts = [e.artifact.parts[0].root.text for e in q.events
                      if hasattr(e, "artifact") and e.artifact.name == "analysis"]
    assert text_artifacts, "no analysis artifact emitted"
    combined = "\n".join(text_artifacts)
    assert "meditation" in combined
    assert "cold-shower" in combined
    assert "3d" in combined or "3 day" in combined


@pytest.mark.asyncio
async def test_archive_habit_happy_path():
    from agents.habits.app.executor import HabitsAgentExecutor

    archived = {}

    async def fake_archive(habit_id):
        archived["id"] = habit_id
        return True

    async def fake_find(name):
        return {"id": "h-42", "name": "meditation"} if name == "meditation" else None

    with patch("agents.habits.app.executor._get_llm", return_value=_fake_llm("")), \
         patch("agents.habits.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.habits.app.executor.registry.find_by_name", new=fake_find), \
         patch("agents.habits.app.executor.registry.archive", new=fake_archive), \
         patch("agents.habits.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[])):
        q = _Queue()
        await HabitsAgentExecutor().execute(
            _Ctx("/habit stop meditation", skill="archive_habit",
                 params={"name": "meditation"}),
            q,
        )
    assert archived["id"] == "h-42"


@pytest.mark.asyncio
async def test_archive_habit_not_found_completes_gracefully():
    from agents.habits.app.executor import HabitsAgentExecutor

    async def fake_find(name):
        return None

    async def fake_archive(habit_id):
        # should not be called when name is unknown
        raise AssertionError("archive must not be invoked when habit is missing")

    with patch("agents.habits.app.executor._get_llm", return_value=_fake_llm("")), \
         patch("agents.habits.app.executor.insert_task_record", new=AsyncMock()), \
         patch("agents.habits.app.executor.registry.find_by_name", new=fake_find), \
         patch("agents.habits.app.executor.registry.archive", new=fake_archive), \
         patch("agents.habits.app.executor.upsert_memory", new=AsyncMock()), \
         patch("agents.habits.app.prompt.fetch_active_habits",
               new=AsyncMock(return_value=[])), \
         patch("agents.habits.app.prompt.fetch_habit_logs",
               new=AsyncMock(return_value=[])):
        q = _Queue()
        await HabitsAgentExecutor().execute(
            _Ctx("/habit stop nope", skill="archive_habit",
                 params={"name": "nope"}),
            q,
        )

    states = [e.status.state for e in q.events if hasattr(e, "status")]
    assert TaskState.completed in states
    text_artifacts = [e.artifact.parts[0].root.text for e in q.events
                      if hasattr(e, "artifact") and e.artifact.name == "analysis"]
    assert any("not found" in t for t in text_artifacts)
