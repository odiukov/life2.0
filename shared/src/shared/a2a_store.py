"""Postgres-backed TaskStore for the A2A SDK."""
from __future__ import annotations

from typing import Any

from a2a.server.tasks import TaskStore
from a2a.types import Artifact, Task, TaskState, TaskStatus, TextPart

from .db import get_pool


def _part_text(p: Any) -> str | None:
    # Part objects wrap a root TextPart/FilePart/DataPart; grab text when present.
    root = getattr(p, "root", p)
    return getattr(root, "text", None)


def _artifact_to_dict(a: Artifact) -> dict[str, Any]:
    return {
        "artifact_id": a.artifact_id,
        "name": a.name,
        "parts": [{"type": "text", "text": _part_text(p) or ""} for p in a.parts],
    }


def _dict_to_artifact(d: dict[str, Any]) -> Artifact:
    parts = [TextPart(text=p.get("text", "")) for p in d.get("parts", [])]
    return Artifact(
        artifact_id=d.get("artifact_id") or d.get("artifactId") or "artifact",
        name=d.get("name", ""),
        parts=parts,
    )


def _first_text(artifacts: list[dict[str, Any]]) -> str | None:
    for a in artifacts:
        for p in a.get("parts", []):
            if p.get("text"):
                return p["text"]
    return None


class PostgresTaskStore(TaskStore):
    """Store A2A Task objects in the shared tasks table, scoped by agent."""

    def __init__(self, agent: str):
        self.agent = agent

    async def save(self, task: Task, context=None) -> None:
        pool = await get_pool()
        artifacts = [_artifact_to_dict(a) for a in (task.artifacts or [])]
        history = [m.model_dump(mode="json") for m in (task.history or [])]
        skill_id = (task.metadata or {}).get("skillId") if task.metadata else None
        state_val = task.status.state.value if hasattr(task.status.state, "value") else str(task.status.state)
        await pool.execute(
            """
            INSERT INTO tasks (task_id, context_id, agent, skill_id, state, input, output, artifacts, history)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9)
            ON CONFLICT (task_id) DO UPDATE SET
                state = EXCLUDED.state,
                artifacts = EXCLUDED.artifacts,
                history = EXCLUDED.history,
                updated_at = NOW()
            """,
            task.id,
            task.context_id,
            self.agent,
            skill_id,
            state_val,
            {},
            _first_text(artifacts),
            artifacts,
            history,
        )

    async def get(self, task_id: str, context=None) -> Task | None:
        pool = await get_pool()
        row = await pool.fetchrow(
            "SELECT task_id, context_id, state, skill_id, artifacts, history "
            "FROM tasks WHERE task_id = $1 AND agent = $2",
            task_id, self.agent,
        )
        if row is None:
            return None
        artifacts = [_dict_to_artifact(a) for a in (row["artifacts"] or [])]
        state = TaskState(row["state"]) if row["state"] else TaskState.submitted
        metadata = {"skillId": row["skill_id"]} if row["skill_id"] else None
        return Task(
            id=str(row["task_id"]),
            context_id=str(row["context_id"]) if row["context_id"] else None,
            status=TaskStatus(state=state),
            artifacts=artifacts,
            history=[],
            metadata=metadata,
        )

    async def delete(self, task_id: str, context=None) -> None:
        pool = await get_pool()
        await pool.execute(
            "DELETE FROM tasks WHERE task_id = $1 AND agent = $2",
            task_id, self.agent,
        )
