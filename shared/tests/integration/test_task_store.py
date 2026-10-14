import logging
from types import MappingProxyType
from uuid import UUID, uuid4

import pytest
from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from a2a.types import Artifact, DataPart, Message, Part, Role, Task, TaskState, TaskStatus, TextPart
from shared.adapters.a2a.task_records import SqlTaskRecords
from shared.adapters.a2a.task_store import SqlTaskStore
from shared.ports.tasks import TaskRecords
from shared.schema.tables import tasks
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration


def task(state: TaskState, text_value: str = "hello") -> Task:
    return Task(
        id=str(uuid4()),
        context_id=str(uuid4()),
        status=TaskStatus(state=state),
        artifacts=[
            Artifact(
                artifact_id="a1", name="analysis", parts=[Part(root=TextPart(text=text_value))]
            )
        ],
        history=[],
        metadata={"skillId": "log_meal"},
    )


@pytest.fixture
async def engine(clean_db: PostgresUrls):
    engine = create_async_engine(clean_db.rw)
    try:
        yield engine
    finally:
        await engine.dispose()


@pytest.mark.parametrize("state", list(TaskState))
async def test_save_get_round_trip(engine, state) -> None:
    store: TaskStore = SqlTaskStore(engine, agent="nutrition")
    saved = task(state)
    context = ServerCallContext()
    await store.save(saved, context=context)
    got = await store.get(saved.id, context=context)
    assert isinstance(got, Task)
    assert got.id == saved.id
    assert got.context_id == saved.context_id
    assert got.status.state is state
    assert got.metadata == {"skillId": "log_meal"}
    assert got.artifacts is not None
    assert isinstance(got.artifacts[0], Artifact)
    assert got.artifacts[0].name == "analysis"
    assert isinstance(got.artifacts[0].parts[0], Part)
    assert isinstance(got.artifacts[0].parts[0].root, TextPart)
    assert got.artifacts[0].parts[0].root.text == "hello"


async def test_save_twice_updates_state_artifacts_and_history_only(engine) -> None:
    store = SqlTaskStore(engine, agent="nutrition")
    first = task(TaskState.working, "initial output")
    await store.save(first)
    async with engine.connect() as conn:
        before = (await conn.execute(select(tasks).where(tasks.c.task_id == UUID(first.id)))).one()
    history = Message(
        message_id="m1", role=Role.user, parts=[Part(root=TextPart(text="new user message"))]
    )
    changed = first.model_copy(
        update={
            "status": TaskStatus(state=TaskState.completed),
            "context_id": str(uuid4()),
            "metadata": {"skillId": "analyze_nutrition"},
            "artifacts": task(TaskState.completed, "new output").artifacts,
            "history": [history],
        }
    )
    await store.save(changed)
    got = await store.get(first.id)
    assert got is not None
    assert got.status.state is TaskState.completed
    assert got.context_id == first.context_id
    assert got.metadata == {"skillId": "log_meal"}
    assert got.history == []
    assert got.artifacts[0].parts[0].root.text == "new output"
    async with engine.connect() as conn:
        after = (await conn.execute(select(tasks).where(tasks.c.task_id == UUID(first.id)))).one()
    assert after.id == before.id
    assert after.created_at == before.created_at
    assert after.updated_at > before.updated_at
    assert after.output == "initial output"
    assert after.input == {}
    assert after.history == [history.model_dump(mode="json")]


async def test_tasks_are_scoped_by_agent_and_deletable(engine) -> None:
    saved = task(TaskState.completed)
    nutrition = SqlTaskStore(engine, agent="nutrition")
    sleep = SqlTaskStore(engine, agent="sleep")
    await nutrition.save(saved)
    assert await sleep.get(saved.id) is None
    await sleep.delete(saved.id)
    assert await nutrition.get(saved.id) is not None
    await nutrition.delete(saved.id, context=ServerCallContext())
    assert await nutrition.get(saved.id) is None
    await nutrition.delete(saved.id)
    assert await nutrition.get(str(uuid4())) is None


async def test_artifact_order_and_legacy_text_projection(engine) -> None:
    saved = task(TaskState.completed)
    saved.artifacts = [
        Artifact(
            artifact_id="entry",
            name="log_entry",
            parts=[Part(root=DataPart(data={"calories": 123})), Part(root=TextPart(text=""))],
        ),
        Artifact(
            artifact_id="peers",
            name="consulted_peers",
            parts=[Part(root=TextPart(text="sleep"))],
        ),
        Artifact(
            artifact_id="answer",
            name="analysis",
            parts=[Part(root=TextPart(text="analysis output"))],
        ),
    ]
    saved.metadata = {"skillId": "log_meal", "other": "legacy drops extra metadata"}
    store = SqlTaskStore(engine, agent="nutrition")
    await store.save(saved)
    got = await store.get(saved.id)
    assert got is not None
    assert [a.name for a in got.artifacts] == ["log_entry", "consulted_peers", "analysis"]
    assert [a.artifact_id for a in got.artifacts] == ["entry", "peers", "answer"]
    assert [p.root.text for p in got.artifacts[0].parts] == ["", ""]
    assert got.metadata == {"skillId": "log_meal"}
    async with engine.connect() as conn:
        row = (await conn.execute(select(tasks).where(tasks.c.task_id == UUID(saved.id)))).one()
    assert row.output == "sleep"
    assert row.artifacts[0] == {
        "artifact_id": "entry",
        "name": "log_entry",
        "parts": [{"type": "text", "text": ""}, {"type": "text", "text": ""}],
    }


async def test_get_loads_legacy_artifact_keys_and_null_context(engine) -> None:
    task_id = uuid4()
    async with engine.begin() as conn:
        await conn.execute(
            insert(tasks).values(
                task_id=task_id,
                agent="nutrition",
                state="submitted",
                artifacts=[{"artifactId": "old", "parts": [{"text": "legacy"}]}, {}],
            )
        )
    got = await SqlTaskStore(engine, agent="nutrition").get(str(task_id))
    assert got is not None
    assert got.context_id == ""
    assert got.metadata is None
    assert got.history == []
    assert got.artifacts[0].artifact_id == "old"
    assert got.artifacts[0].name == ""
    assert got.artifacts[0].parts[0].root.text == "legacy"
    assert got.artifacts[1].artifact_id == "artifact"
    assert got.artifacts[1].parts == []


async def test_save_empty_task_has_no_output_or_skill(engine) -> None:
    saved = task(TaskState.submitted)
    saved.context_id = ""
    saved.artifacts = None
    saved.history = None
    saved.metadata = {"skillId": 123}
    store = SqlTaskStore(engine, agent="nutrition")
    await store.save(saved)
    got = await store.get(saved.id)
    assert got is not None
    assert got.context_id == ""
    assert got.artifacts == []
    assert got.history == []
    assert got.metadata is None
    async with engine.connect() as conn:
        row = (await conn.execute(select(tasks).where(tasks.c.task_id == UUID(saved.id)))).one()
    assert row.output is None
    assert row.context_id is None
    assert row.artifacts == []
    assert row.history == []


async def test_task_records_upsert_output_and_state_preserves_initial_input(engine) -> None:
    records: TaskRecords = SqlTaskRecords(engine)
    task_id, context_id = str(uuid4()), str(uuid4())
    await records.record(
        agent="nutrition",
        task_id=task_id,
        context_id=context_id,
        skill_id="log_meal",
        input_=MappingProxyType({"message": "овсянка"}),
        output="first",
        state="working",
    )
    async with engine.connect() as conn:
        before = (await conn.execute(select(tasks).where(tasks.c.task_id == UUID(task_id)))).one()
    await records.record(
        agent="sleep",
        task_id=task_id,
        context_id=str(uuid4()),
        skill_id="other",
        input_={"message": "changed"},
        output="second",
        state="completed",
    )
    async with engine.connect() as conn:
        row = (await conn.execute(select(tasks).where(tasks.c.task_id == UUID(task_id)))).one()
    assert (row.output, row.state, row.input) == ("second", "completed", {"message": "овсянка"})
    assert row.agent == "nutrition"
    assert row.skill_id == "log_meal"
    assert row.context_id == UUID(context_id)
    assert row.id == before.id
    assert row.created_at == before.created_at
    assert row.updated_at > before.updated_at


async def test_task_records_allow_null_context(engine) -> None:
    task_id = str(uuid4())
    await SqlTaskRecords(engine).record(
        agent="nutrition",
        task_id=task_id,
        context_id=None,
        skill_id="log_meal",
        input_={},
        output="done",
        state="completed",
    )
    got = await SqlTaskStore(engine, agent="nutrition").get(task_id)
    assert got is not None
    assert got.context_id == ""
    assert got.artifacts == []
    assert got.status.state is TaskState.completed


async def test_store_and_records_share_rows_without_overwriting_each_others_payloads(
    engine, caplog
) -> None:
    caplog.set_level(logging.INFO)
    saved = task(TaskState.working, "private artifact output")
    saved.history = [
        Message(
            message_id="m1",
            role=Role.user,
            parts=[Part(root=TextPart(text="private user history"))],
        )
    ]
    records = SqlTaskRecords(engine)
    await records.record(
        agent="nutrition",
        task_id=saved.id,
        context_id=saved.context_id,
        skill_id="log_meal",
        input_={"message": "private user message"},
        output="private record output",
        state="submitted",
    )
    store = SqlTaskStore(engine, agent="nutrition")
    await store.save(saved)
    async with engine.connect() as conn:
        row = (await conn.execute(select(tasks).where(tasks.c.task_id == UUID(saved.id)))).one()
    assert row.state == "working"
    assert row.input == {"message": "private user message"}
    assert row.output == "private record output"
    assert row.artifacts[0]["parts"][0]["text"] == "private artifact output"
    assert row.history[0]["parts"][0]["text"] == "private user history"
    got = await store.get(saved.id)
    assert got is not None
    assert got.artifacts[0].parts[0].root.text == "private artifact output"
    await store.delete(saved.id)
    assert not any("private " in record.getMessage() for record in caplog.records)
