"""HTTP-level tests for /agent/{name}/stream pass-through."""
from __future__ import annotations

import json
from typing import AsyncIterator
from uuid import UUID

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from orchestrator.app.agent_passthrough import router as passthrough_router


def _parse_sse(body: str) -> list[dict]:
    events = []
    for frame in body.strip().split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


@pytest.fixture
def app(monkeypatch):
    """Build a minimal FastAPI app with auth dependency stubbed."""
    from orchestrator.app.auth import current_user

    app = FastAPI()
    app.include_router(passthrough_router)
    app.dependency_overrides[current_user] = lambda: UUID("00000000-0000-0000-0000-000000000001")
    return app


def test_unknown_agent_returns_404(app, monkeypatch):
    from orchestrator.app import agent_passthrough as ap
    monkeypatch.setattr(ap, "get_agent_url", lambda _name: None)
    client = TestClient(app)
    resp = client.post("/agent/nonexistent/stream", json={"messages": [{"role": "user", "content": "hi"}]})
    assert resp.status_code == 404


def test_happy_path_emits_routed_text_consulted_finished(app, monkeypatch):
    from orchestrator.app import agent_passthrough as ap

    monkeypatch.setattr(ap, "get_agent_url", lambda _n: "http://sleep:8001")

    async def _fake_call(*, agent: str, message: str, user_id: str) -> AsyncIterator[dict]:
        yield {"type": "text", "delta": "hello "}
        yield {"type": "text", "delta": "world"}
        yield {"type": "consulted", "peers": ["nutrition", "workout"]}

    monkeypatch.setattr(ap, "stream_peer_call", _fake_call)

    client = TestClient(app)
    resp = client.post(
        "/agent/sleep/stream",
        json={"messages": [{"role": "user", "content": "how did I sleep"}], "threadId": "t1"},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]

    assert types[0] == "RunStarted"
    assert types[1] == "TextMessageStart"
    routed = next(e for e in events if e["type"] == "AgentRouted")
    assert routed["primary"] == "sleep"
    assert "TextMessageContent" in types
    consulted = next(e for e in events if e["type"] == "AgentConsulted")
    assert consulted["peers"] == ["nutrition", "workout"]
    assert types[-1] == "RunFinished"


def test_peer_error_emits_error_text_and_finishes(app, monkeypatch):
    from orchestrator.app import agent_passthrough as ap

    monkeypatch.setattr(ap, "get_agent_url", lambda _n: "http://sleep:8001")

    async def _fake_call(*, agent: str, message: str, user_id: str):
        raise RuntimeError("peer down")
        yield  # pragma: no cover  -- make it an async generator

    monkeypatch.setattr(ap, "stream_peer_call", _fake_call)

    client = TestClient(app)
    resp = client.post(
        "/agent/sleep/stream",
        json={"messages": [{"role": "user", "content": "x"}]},
    )
    assert resp.status_code == 200
    events = _parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert "AgentRouted" in types
    assert any("peer down" in (e.get("delta") or "") for e in events if e["type"] == "TextMessageContent")
    assert types[-1] == "RunFinished"


@pytest.mark.asyncio
async def test_stream_peer_call_extracts_analysis_and_consulted_peers(monkeypatch):
    """stream_peer_call yields normalized events from real A2A artifacts."""
    from orchestrator.app import agent_passthrough as ap
    from a2a.types import (
        Artifact, DataPart, Message as A2AMessage, Part, Task, TaskState, TaskStatus, TextPart,
    )

    monkeypatch.setattr(ap, "get_agent_url", lambda _n: "http://sleep:8001")

    class FakeA2AClient:
        async def send_message(self, _msg):
            task = Task(
                id="t-fake",
                context_id="c-fake",
                status=TaskStatus(state=TaskState.completed),
                artifacts=[
                    Artifact(
                        artifact_id="a1", name="analysis",
                        parts=[Part(root=TextPart(text="You slept 7h."))],
                    ),
                    Artifact(
                        artifact_id="a2", name="consulted_peers",
                        parts=[Part(root=DataPart(data={"peers": ["nutrition"]}))],
                    ),
                ],
            )
            yield (task, None)

    async def _fake_get_client(_url):
        return FakeA2AClient()

    monkeypatch.setattr(ap, "get_client", _fake_get_client)

    events = []
    async for ev in ap.stream_peer_call(agent="sleep", message="hi", user_id="u1"):
        events.append(ev)

    assert {"type": "text", "delta": "You slept 7h."} in events
    assert {"type": "consulted", "peers": ["nutrition"]} in events
