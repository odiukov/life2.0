"""Emit a `consulted_peers` artifact so callers can see which peer agents
were consulted by an A2A peer during a single skill run."""
from __future__ import annotations

import uuid
from typing import Iterable

from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    DataPart,
    Part,
    TaskArtifactUpdateEvent,
)


async def emit_consulted_peers_artifact(
    event_queue: EventQueue,
    task_id: str,
    context_id: str,
    peers: Iterable[str],
) -> None:
    """Emit a `consulted_peers` artifact with the names of peers consulted.

    Always emitted, even with an empty list — frontends rely on the artifact's
    presence to distinguish "no peers consulted" from "the peer call dropped".
    """
    peer_list = list(peers)
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name="consulted_peers",
        parts=[Part(root=DataPart(data={"peers": peer_list}))],
    )
    evt = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=artifact,
        append=False,
        last_chunk=True,
    )
    await event_queue.enqueue_event(evt)
