"""Tests for the consulted_peers artifact helper."""
from __future__ import annotations

import pytest
from a2a.types import DataPart, TaskArtifactUpdateEvent

from shared.consulted import emit_consulted_peers_artifact


class FakeQueue:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def enqueue_event(self, evt: object) -> None:
        self.events.append(evt)


@pytest.mark.asyncio
async def test_emits_artifact_with_peer_names() -> None:
    q = FakeQueue()
    await emit_consulted_peers_artifact(q, "task-1", "ctx-1", ["nutrition", "workout"])
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, TaskArtifactUpdateEvent)
    assert evt.artifact.name == "consulted_peers"
    assert evt.task_id == "task-1"
    assert evt.context_id == "ctx-1"
    part = evt.artifact.parts[0].root
    assert isinstance(part, DataPart)
    assert part.data == {"peers": ["nutrition", "workout"]}


@pytest.mark.asyncio
async def test_emits_empty_artifact_when_peers_empty() -> None:
    q = FakeQueue()
    await emit_consulted_peers_artifact(q, "task-1", "ctx-1", [])
    assert len(q.events) == 1
    evt = q.events[0]
    assert isinstance(evt, TaskArtifactUpdateEvent)
    assert evt.artifact.name == "consulted_peers"
    part = evt.artifact.parts[0].root
    assert isinstance(part, DataPart)
    assert part.data == {"peers": []}
