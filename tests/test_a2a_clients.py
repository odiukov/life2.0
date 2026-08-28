import pytest
from unittest.mock import AsyncMock, patch

from a2a.types import AgentCard, AgentCapabilities


@pytest.fixture(autouse=True)
def reset_caches():
    from shared import a2a_clients
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
    from shared import a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.a2a_clients.A2ACardResolver", return_value=resolver):
        c1 = await a2a_clients.get_card("http://agent-sleep:8001")
        c2 = await a2a_clients.get_card("http://agent-sleep:8001")

    assert c1.name == "sleep-agent"
    assert c1 is c2
    assert resolver.get_agent_card.await_count == 1


@pytest.mark.asyncio
async def test_get_card_normalizes_trailing_slash():
    from shared import a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.a2a_clients.A2ACardResolver", return_value=resolver):
        c1 = await a2a_clients.get_card("http://agent-sleep:8001")
        c2 = await a2a_clients.get_card("http://agent-sleep:8001/")

    assert c1 is c2
    assert resolver.get_agent_card.await_count == 1


@pytest.mark.asyncio
async def test_get_client_uses_cached_card():
    from shared import a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.a2a_clients.A2ACardResolver", return_value=resolver):
        client = await a2a_clients.get_client("http://agent-sleep:8001")
    assert client is not None

    # Second call returns cached instance (resolver shouldn't even be constructed again)
    with patch("shared.a2a_clients.A2ACardResolver", return_value=resolver):
        client2 = await a2a_clients.get_client("http://agent-sleep:8001")
    assert client is client2


@pytest.mark.asyncio
async def test_clear_caches_drops_everything():
    from shared import a2a_clients

    resolver = AsyncMock()
    resolver.get_agent_card = AsyncMock(return_value=_card())
    with patch("shared.a2a_clients.A2ACardResolver", return_value=resolver):
        await a2a_clients.get_client("http://agent-sleep:8001")

    assert a2a_clients._card_cache
    assert a2a_clients._client_cache
    a2a_clients.clear_caches()
    assert not a2a_clients._card_cache
    assert not a2a_clients._client_cache
