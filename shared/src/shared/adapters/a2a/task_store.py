"""A2A TaskStore on SQLAlchemy; same rows and serialization as legacy PostgresTaskStore."""

from __future__ import annotations

from typing import Any
from uuid import UUID

from a2a.server.context import ServerCallContext
from a2a.server.tasks import TaskStore
from a2a.types import Artifact, Part, Task, TaskState, TaskStatus, TextPart
from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.schema.tables import tasks


def _part_text(part: Any) -> str | None:
    root = getattr(part, "root", part)
    value = getattr(root, "text", None)
    return value if isinstance(value, str) else None


def _artifact_to_dict(artifact: Artifact) -> dict[str, Any]:
    return {
        "artifact_id": artifact.artifact_id,
        "name": artifact.name,
        "parts": [{"type": "text", "text": _part_text(p) or ""} for p in artifact.parts],
    }


def _dict_to_artifact(data: dict[str, Any]) -> Artifact:
    return Artifact(
        artifact_id=data.get("artifact_id") or data.get("artifactId") or "artifact",
        name=data.get("name", ""),
        parts=[Part(root=TextPart(text=p.get("text", ""))) for p in data.get("parts", [])],
    )


def _first_text(artifacts: list[dict[str, Any]]) -> str | None:
    for artifact in artifacts:
        for part in artifact.get("parts", []):
            if part.get("text"):
                return str(part["text"])
    return None


def _uuid(value: str | None) -> UUID | None:
    return UUID(value) if value else None


class SqlTaskStore(TaskStore):
    def __init__(self, engine: AsyncEngine, *, agent: str) -> None:
        self._engine = engine
        self._agent = agent

    async def save(self, task: Task, context: ServerCallContext | None = None) -> None:
        artifacts = [_artifact_to_dict(a) for a in task.artifacts or []]
        history = [m.model_dump(mode="json") for m in task.history or []]
        skill_id = (task.metadata or {}).get("skillId")
        statement = insert(tasks).values(
            task_id=UUID(task.id),
            context_id=_uuid(task.context_id),
            agent=self._agent,
            skill_id=skill_id if isinstance(skill_id, str) else None,
            state=task.status.state.value,
            input={},
            output=_first_text(artifacts),
            artifacts=artifacts,
            history=history,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[tasks.c.task_id],
            set_={
                "state": statement.excluded.state,
                "artifacts": statement.excluded.artifacts,
                "history": statement.excluded.history,
                "updated_at": func.now(),
            },
        )
        async with self._engine.begin() as conn:
            await conn.execute(statement)

    async def get(self, task_id: str, context: ServerCallContext | None = None) -> Task | None:
        query = select(
            tasks.c.task_id, tasks.c.context_id, tasks.c.state, tasks.c.skill_id, tasks.c.artifacts
        ).where(tasks.c.task_id == UUID(task_id), tasks.c.agent == self._agent)
        async with self._engine.connect() as conn:
            row = (await conn.execute(query)).one_or_none()
        if row is None:
            return None
        return Task(
            id=str(row.task_id),
            context_id=str(row.context_id) if row.context_id else "",
            status=TaskStatus(state=TaskState(row.state) if row.state else TaskState.submitted),
            artifacts=[_dict_to_artifact(a) for a in row.artifacts or []],
            history=[],
            metadata={"skillId": row.skill_id} if row.skill_id else None,
        )

    async def delete(self, task_id: str, context: ServerCallContext | None = None) -> None:
        async with self._engine.begin() as conn:
            await conn.execute(
                delete(tasks).where(tasks.c.task_id == UUID(task_id), tasks.c.agent == self._agent)
            )
