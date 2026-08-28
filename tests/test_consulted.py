"""consulted_peers artifact must always be emitted, even when the peer
list is empty — frontend distinguishes 'no peers consulted' from
'call dropped'."""
import pytest

pytestmark = pytest.mark.asyncio


class _FakeQueue:
    def __init__(self):
        self.events = []

    async def enqueue_event(self, evt):
        self.events.append(evt)


async def test_emit_consulted_peers_emits_even_when_empty():
    from shared.consulted import emit_consulted_peers_artifact
    from a2a.types import DataPart

    q = _FakeQueue()
    await emit_consulted_peers_artifact(q, "task-1", "ctx-1", [])

    assert len(q.events) == 1
    art = q.events[0].artifact
    assert art.name == "consulted_peers"
    root = getattr(art.parts[0], "root", art.parts[0])
    assert isinstance(root, DataPart)
    assert root.data == {"peers": []}


async def test_emit_consulted_peers_emits_with_names():
    from shared.consulted import emit_consulted_peers_artifact

    q = _FakeQueue()
    await emit_consulted_peers_artifact(q, "task-1", "ctx-1", ["sleep", "workout"])

    assert len(q.events) == 1
    art = q.events[0].artifact
    root = getattr(art.parts[0], "root", art.parts[0])
    assert root.data == {"peers": ["sleep", "workout"]}
