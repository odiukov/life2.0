"""/chat/stream emits AgentRouted and AgentConsulted derived from LangGraph state."""
from __future__ import annotations

import json

from fastapi.testclient import TestClient


def _parse_sse(body: str) -> list[dict]:
    events = []
    for frame in body.strip().split("\n\n"):
        for line in frame.splitlines():
            if line.startswith("data: "):
                events.append(json.loads(line[len("data: "):]))
    return events


def test_chat_stream_includes_routed_and_consulted(monkeypatch):
    """When the routing iterator yields a primary peer + consulted peers, both events are emitted."""
    from orchestrator.app import main as omain
    from orchestrator.app.auth import current_user
    from uuid import UUID

    async def _fake_run_graph_iter(_text, _user_id, _thread_id, _user_timezone=None):
        # Tuple shape: (primary, consulted, content)
        yield ("sleep", ["nutrition"], "ok")

    monkeypatch.setattr(omain, "_run_graph_with_routing", _fake_run_graph_iter)
    omain.app.dependency_overrides[current_user] = lambda: UUID("00000000-0000-0000-0000-000000000001")
    try:
        client = TestClient(omain.app)
        resp = client.post(
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "how did I sleep"}], "threadId": "t1"},
        )
        assert resp.status_code == 200
        events = _parse_sse(resp.text)
        routed = next(e for e in events if e["type"] == "AgentRouted")
        assert routed["primary"] == "sleep"
        consulted = next(e for e in events if e["type"] == "AgentConsulted")
        assert consulted["peers"] == ["nutrition"]
    finally:
        omain.app.dependency_overrides.clear()


def test_chat_stream_main_when_no_peer_called(monkeypatch):
    """Synthesis-only response → primary='main', no AgentConsulted event."""
    from orchestrator.app import main as omain
    from orchestrator.app.auth import current_user
    from uuid import UUID

    async def _fake_run_graph_iter(_text, _user_id, _thread_id, _user_timezone=None):
        yield ("main", [], "hi")

    monkeypatch.setattr(omain, "_run_graph_with_routing", _fake_run_graph_iter)
    omain.app.dependency_overrides[current_user] = lambda: UUID("00000000-0000-0000-0000-000000000001")
    try:
        client = TestClient(omain.app)
        resp = client.post("/chat/stream", json={"messages": [{"role": "user", "content": "hello"}]})
        events = _parse_sse(resp.text)
        routed = next(e for e in events if e["type"] == "AgentRouted")
        assert routed["primary"] == "main"
        assert not any(e["type"] == "AgentConsulted" for e in events)
    finally:
        omain.app.dependency_overrides.clear()


def test_run_graph_with_routing_accumulates_parallel_tool_updates(monkeypatch):
    """Parallel peer-tool events each carry only their own done-call.

    `_run_peer_tool` snapshots `state.toolCalls` BEFORE running, so when LangGraph
    fans out N peers in parallel, each emits one update with `toolCalls=[just_my_done]`.
    The router must accumulate observed peers across updates; if it resets the
    accumulator per-event, `consulted` ends up empty and only the last peer to
    finish appears in the AgentHeader (the bug from the screenshot).
    """
    import asyncio

    from langchain_core.messages import AIMessage, ToolMessage

    from orchestrator.app import main as omain

    def _done(name: str, idx: int) -> dict:
        return {
            "id": f"call-{idx}",
            "name": name,
            "skill": "x",
            "status": "done",
            "startedAt": "t",
            "endedAt": "t",
        }

    async def _fake_astream(_inputs, config=None):
        # Three parallel tool nodes — each carries its own one done-call.
        yield {"tool_workout": {
            "toolCalls": [_done("ask_workout_agent", 1)],
            "messages": [ToolMessage(content="w", tool_call_id="call-1")],
        }}
        yield {"tool_nutrition": {
            "toolCalls": [_done("ask_nutrition_agent", 2)],
            "messages": [ToolMessage(content="n", tool_call_id="call-2")],
        }}
        yield {"tool_sleep": {
            "toolCalls": [_done("ask_sleep_agent", 3)],
            "messages": [ToolMessage(content="s", tool_call_id="call-3")],
        }}
        # Final synthesis — no toolCalls, just the assistant message.
        yield {"agent": {
            "messages": [AIMessage(content="here is the combined plan")],
        }}

    fake_graph = type("FakeGraph", (), {"astream": staticmethod(_fake_astream)})()
    monkeypatch.setattr(omain, "_graph", fake_graph)

    async def _collect():
        return [t async for t in omain._run_graph_with_routing("hi", "u1", "t1")]

    results = asyncio.run(_collect())
    assert results, "expected at least one yielded (primary, consulted, content) tuple"
    primary, consulted, content = results[-1]
    assert primary == "sleep", f"last-finished peer should be primary, got {primary}"
    assert set(consulted) == {"workout", "nutrition"}, (
        f"all earlier peers should be consulted, got {consulted}"
    )
    assert "combined plan" in content


def test_chat_stream_passes_user_timezone_to_graph(monkeypatch):
    from orchestrator.app import main as omain
    from orchestrator.app.auth import current_user
    from uuid import UUID

    captured = {}

    async def _fake_run_graph_iter(_text, _user_id, _thread_id, _user_timezone=None):
        captured["timezone"] = _user_timezone
        yield ("main", [], "ok")

    monkeypatch.setattr(omain, "_run_graph_with_routing", _fake_run_graph_iter)
    omain.app.dependency_overrides[current_user] = lambda: UUID("00000000-0000-0000-0000-000000000001")
    try:
        client = TestClient(omain.app)
        resp = client.post(
            "/chat/stream",
            json={
                "messages": [{"role": "user", "content": "what is on my calendar today"}],
                "userTimezone": "Europe/Lisbon",
            },
        )
        assert resp.status_code == 200
        assert captured["timezone"] == "Europe/Lisbon"
    finally:
        omain.app.dependency_overrides.clear()
