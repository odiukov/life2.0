"""A2A events in exactly the shapes the orchestrator and the mobile app already read."""

from __future__ import annotations

import uuid
from collections.abc import Iterable
from datetime import datetime

from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)

LOG_ENTRY_SUMMARY_MAX = 120


def _artifact_event(task_id: str, context_id: str, artifact: Artifact) -> TaskArtifactUpdateEvent:
    return TaskArtifactUpdateEvent(
        task_id=task_id, context_id=context_id, artifact=artifact, append=False, last_chunk=True
    )


def status_event(
    task_id: str,
    context_id: str,
    state: TaskState,
    *,
    error: str | None = None,
    final: bool = False,
) -> TaskStatusUpdateEvent:
    status = TaskStatus(state=state)
    if error:
        status.message = Message(
            role=Role.agent, parts=[Part(root=TextPart(text=error))], message_id=str(uuid.uuid4())
        )
    return TaskStatusUpdateEvent(task_id=task_id, context_id=context_id, status=status, final=final)


def text_artifact_event(
    task_id: str, context_id: str, name: str, text: str
) -> TaskArtifactUpdateEvent:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()), name=name, parts=[Part(root=TextPart(text=text))]
    )
    return _artifact_event(task_id, context_id, artifact)


def _clip(text: str) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= LOG_ENTRY_SUMMARY_MAX:
        return cleaned
    return cleaned[: LOG_ENTRY_SUMMARY_MAX - 1] + "…"


def log_entry_event(
    task_id: str, context_id: str, summary: str, recorded_at: datetime
) -> TaskArtifactUpdateEvent:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name="log_entry",
        parts=[
            Part(
                root=DataPart(
                    data={"summary": _clip(summary), "timestamp": recorded_at.isoformat()}
                )
            )
        ],
    )
    return _artifact_event(task_id, context_id, artifact)


def consulted_peers_event(
    task_id: str, context_id: str, peers: Iterable[str]
) -> TaskArtifactUpdateEvent:
    """Always emitted, even when empty: clients use its presence to tell 'none' from 'dropped'."""
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name="consulted_peers",
        parts=[Part(root=DataPart(data={"peers": list(peers)}))],
    )
    return _artifact_event(task_id, context_id, artifact)
