import pytest
from unittest.mock import AsyncMock, patch

from a2a.types import Task, TaskStatus, TaskState, Artifact, TextPart


def _make_task(task_id="task-1", state=TaskState.completed):
    return Task(
        id=task_id,
        context_id="ctx-1",
        status=TaskStatus(state=state),
        artifacts=[Artifact(artifact_id="a-1", name="analysis", parts=[TextPart(text="hello")])],
        history=[],
    )


@pytest.mark.asyncio
async def test_save_inserts_row():
    from shared.a2a_store import PostgresTaskStore

    fake_pool = AsyncMock()
    fake_pool.execute = AsyncMock()
    with patch("shared.a2a_store.get_pool", return_value=fake_pool):
        store = PostgresTaskStore(agent="sleep")
        await store.save(_make_task())

    assert fake_pool.execute.await_count == 1
    sql = fake_pool.execute.await_args.args[0]
    assert "INSERT INTO tasks" in sql
    assert "ON CONFLICT (task_id) DO UPDATE" in sql


@pytest.mark.asyncio
async def test_get_returns_none_when_missing():
    from shared.a2a_store import PostgresTaskStore

    fake_pool = AsyncMock()
    fake_pool.fetchrow = AsyncMock(return_value=None)
    with patch("shared.a2a_store.get_pool", return_value=fake_pool):
        store = PostgresTaskStore(agent="sleep")
        result = await store.get("nope")

    assert result is None


@pytest.mark.asyncio
async def test_get_hydrates_task():
    from shared.a2a_store import PostgresTaskStore

    row = {
        "task_id": "task-1",
        "context_id": "ctx-1",
        "state": "completed",
        "skill_id": "analyze_sleep",
        "artifacts": [{"artifact_id": "a-1", "name": "analysis", "parts": [{"type": "text", "text": "hi"}]}],
        "history": [],
    }
    fake_pool = AsyncMock()
    fake_pool.fetchrow = AsyncMock(return_value=row)
    with patch("shared.a2a_store.get_pool", return_value=fake_pool):
        store = PostgresTaskStore(agent="sleep")
        task = await store.get("task-1")

    assert task is not None
    assert task.id == "task-1"
    assert task.status.state == TaskState.completed
    assert task.artifacts[0].parts[0].root.text == "hi"


@pytest.mark.asyncio
async def test_delete_issues_delete():
    from shared.a2a_store import PostgresTaskStore

    fake_pool = AsyncMock()
    fake_pool.execute = AsyncMock()
    with patch("shared.a2a_store.get_pool", return_value=fake_pool):
        store = PostgresTaskStore(agent="sleep")
        await store.delete("task-1")

    assert fake_pool.execute.await_count == 1
    assert "DELETE FROM tasks" in fake_pool.execute.await_args.args[0]
