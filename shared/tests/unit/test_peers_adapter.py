from unittest.mock import AsyncMock, patch

import pytest
from a2a.types import (
    AgentCapabilities,
    AgentCard,
    Artifact,
    Message,
    Part,
    Role,
    Task,
    TaskState,
    TaskStatus,
    TextPart,
)
from shared.adapters import peers as peer_mod


@pytest.fixture(autouse=True)
def reset_caches():
    from shared.adapters import peers as a2a_clients

    a2a_clients._card_cache.clear()
    a2a_clients._client_cache.clear()
    yield
    a2a_clients._card_cache.clear()
    a2a_clients._client_cache.clear()


def _card(name: str = "sleep-agent", url: str = "http://agent-sleep:8001/") -> AgentCard:
    return AgentCard(
        protocol_version="0.2.5",
        name=name,
        description="test",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=[],
    )


@pytest.mark.asyncio
async def test_get_card_resolves_once_and_caches():
    from shared.adapters import peers as a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.adapters.peers.A2ACardResolver", return_value=resolver):
        c1 = await a2a_clients._get_card("http://agent-sleep:8001")
        c2 = await a2a_clients._get_card("http://agent-sleep:8001")

    assert c1.name == "sleep-agent"
    assert c1 is c2
    assert resolver.get_agent_card.await_count == 1


@pytest.mark.asyncio
async def test_get_card_normalizes_trailing_slash():
    from shared.adapters import peers as a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.adapters.peers.A2ACardResolver", return_value=resolver):
        c1 = await a2a_clients._get_card("http://agent-sleep:8001")
        c2 = await a2a_clients._get_card("http://agent-sleep:8001/")

    assert c1 is c2
    assert resolver.get_agent_card.await_count == 1


@pytest.mark.asyncio
async def test_get_client_uses_cached_card():
    from shared.adapters import peers as a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.adapters.peers.A2ACardResolver", return_value=resolver):
        client = await a2a_clients._get_client("http://agent-sleep:8001")
    assert client is not None

    # Second call returns cached instance (resolver shouldn't even be constructed again)
    with patch("shared.adapters.peers.A2ACardResolver", return_value=resolver):
        client2 = await a2a_clients._get_client("http://agent-sleep:8001")
    assert client is client2


@pytest.mark.asyncio
async def test_clear_caches_drops_everything():
    from shared.adapters import peers as a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.adapters.peers.A2ACardResolver", return_value=resolver):
        await a2a_clients._get_client("http://agent-sleep:8001")

    assert a2a_clients._card_cache
    assert a2a_clients._client_cache
    a2a_clients.clear_caches()
    assert not a2a_clients._card_cache
    assert not a2a_clients._client_cache


"""Tests for shared.adapters.peers — A2A ClientFactory-based peer consultation."""


def _task_with_text(text: str) -> Task:
    artifact = Artifact(
        artifact_id="a1",
        name="peer_analysis",
        parts=[Part(root=TextPart(text=text))],
    )
    return Task(
        id="t1",
        context_id="c1",
        status=TaskStatus(state=TaskState.completed),
        artifacts=[artifact],
    )


def _make_client_yielding(items):
    """Build a mock client whose send_message returns an async generator."""

    async def _send_message(message):
        for it in items:
            yield it

    client = AsyncMock()
    # send_message must be a plain (non-awaitable) function returning an async iterator.
    client.send_message = lambda message: _send_message(message)
    return client


@pytest.mark.asyncio
async def test_fetch_peer_artifacts_returns_task_artifact_text():
    from shared.adapters import peers as peer

    client = _make_client_yielding([(_task_with_text("workout summary"), None)])
    with patch("shared.adapters.peers._get_client", AsyncMock(return_value=client)):
        result = await peer.fetch_peer_artifacts(
            peer_agents={"workout": {"url": "http://agent-workout:8003"}},
            peer_task_names={"workout": "workout_summary"},
        )

    assert result == {"workout": "workout summary"}


@pytest.mark.asyncio
async def test_fetch_peer_artifacts_empty_needed_returns_empty():
    from shared.adapters import peers as peer

    get_client_mock = AsyncMock()
    with patch("shared.adapters.peers._get_client", get_client_mock):
        result = await peer.fetch_peer_artifacts(
            peer_agents={"workout": {"url": "http://agent-workout:8003"}},
            peer_task_names={"workout": "workout_summary"},
            needed=set(),
        )

    assert result == {}
    get_client_mock.assert_not_called()


@pytest.mark.asyncio
async def test_fetch_peer_artifacts_swallows_exception():
    from shared.adapters import peers as peer

    with patch(
        "shared.adapters.peers._get_client",
        AsyncMock(side_effect=RuntimeError("boom")),
    ):
        result = await peer.fetch_peer_artifacts(
            peer_agents={"workout": {"url": "http://agent-workout:8003"}},
            peer_task_names={"workout": "workout_summary"},
        )

    assert result == {"workout": "(данные недоступны)"}


@pytest.mark.asyncio
async def test_call_peer_handles_plain_message_response():
    from shared.adapters import peers as peer

    msg = Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text="simple reply"))],
        message_id="m1",
    )
    client = _make_client_yielding([msg])
    with patch("shared.adapters.peers._get_client", AsyncMock(return_value=client)):
        text = await peer.call_peer("http://agent-x:8000", "some_skill")

    assert text == "simple reply"


"""Depth-1 cap on peer-consult fan-out. call_peer must propagate
is_peer_call=True so the receiving agent's executor knows it's a peer call
and skips its own peer-consult step."""


@pytest.mark.asyncio
async def test_call_peer_propagates_is_peer_call_true_in_metadata():
    captured: dict = {}

    async def _send_message(message):
        captured["metadata"] = dict(message.metadata or {})
        return
        yield  # async generator

    client = AsyncMock()
    client.send_message = lambda message: _send_message(message)

    with patch("shared.adapters.peers._get_client", AsyncMock(return_value=client)):
        await peer_mod.call_peer(
            "http://x:1/",
            "analyze_workout",
            user_id="u1",
            for_date="2026-04-30",
        )

    assert captured["metadata"] == {
        "is_peer_call": True,
        "skillId": "analyze_workout",
        "user_id": "u1",
        "for_date": "2026-04-30",
    }
