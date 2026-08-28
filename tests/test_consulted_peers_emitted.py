"""End-to-end style: each peer's executor emits a `consulted_peers` artifact
when peer_artifacts is non-empty."""
from __future__ import annotations

from unittest.mock import AsyncMock

import pytest
from a2a.types import DataPart, TaskArtifactUpdateEvent

from agents.sleep.app.executor import SleepAgentExecutor


class FakeQueue:
    def __init__(self) -> None:
        self.events: list[object] = []

    async def enqueue_event(self, evt: object) -> None:
        self.events.append(evt)


def _consulted_event(events: list[object]) -> TaskArtifactUpdateEvent | None:
    for e in events:
        if isinstance(e, TaskArtifactUpdateEvent) and e.artifact.name == "consulted_peers":
            return e
    return None


@pytest.mark.asyncio
async def test_sleep_executor_emits_consulted_peers(monkeypatch) -> None:
    """When the sleep executor fetches peer artifacts, it emits a consulted_peers artifact."""
    from agents.sleep.app import executor as sleep_exec

    fake_queue = FakeQueue()

    class FakeCtx:
        task_id = "t1"
        context_id = "c1"
        message = type("M", (), {
            "parts": [type("P", (), {"root": type("R", (), {"text": "analyze"})()})()],
            "metadata": {"skillId": "analyze_sleep"},
        })()

    async def _fake_user_id(_msg):  # noqa: ANN001
        return "user-1"

    async def _fake_peers(*_a, **_k):
        return {"nutrition": "stuff", "workout": "things"}

    monkeypatch.setattr(sleep_exec, "user_id_from_message", _fake_user_id)
    monkeypatch.setattr(sleep_exec, "fetch_peer_artifacts", _fake_peers)
    monkeypatch.setattr(sleep_exec, "insert_task_record", AsyncMock())
    monkeypatch.setattr(sleep_exec, "upsert_memory", AsyncMock())
    monkeypatch.setattr(sleep_exec, "_get_llm", lambda: type("L", (), {
        "ainvoke": AsyncMock(return_value=type("R", (), {"content": "ok"})())
    })())
    # Skip persistence side effects
    async def _fake_prompt(_msg, _params):
        return "prompt"
    monkeypatch.setitem(sleep_exec.SKILL_PROMPTS, "analyze_sleep", _fake_prompt)

    await SleepAgentExecutor().execute(FakeCtx(), fake_queue)
    evt = _consulted_event(fake_queue.events)
    assert evt is not None, "expected consulted_peers artifact to be emitted"
    part = evt.artifact.parts[0].root
    assert isinstance(part, DataPart)
    assert sorted(part.data["peers"]) == ["nutrition", "workout"]
