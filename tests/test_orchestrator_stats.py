import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport
import json


def parse_sse(raw: str) -> list[dict]:
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_stats_endpoint_shape():
    """GET /stats returns the expected JSON shape."""
    mock_pool = AsyncMock()
    mock_pool.fetch = AsyncMock(return_value=[])
    mock_pool.fetchrow = AsyncMock(return_value=None)

    with patch("orchestrator.app.db.get_pool", return_value=mock_pool):
        from orchestrator.app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
            resp = await client.get("/stats")
    assert resp.status_code == 200
    body = resp.json()
    assert "agents" in body
    assert "activity" in body
    assert "sleep" in body["agents"]
    assert "workout" in body["agents"]
    assert "nutrition" in body["agents"]
    for agent in body["agents"].values():
        assert "tasks_week" in agent
        assert "tasks_prev_week" in agent
        assert "delta" in agent


@pytest.mark.asyncio
async def test_chat_stream_sync_intent_calls_sync_service():
    """POST /chat/stream with sync intent calls sync-service and streams result."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"synced": 5, "skipped": 2, "errors": []})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("orchestrator.app.main.classify_intent", return_value="sync"):
        with patch("httpx.AsyncClient", return_value=mock_client):
            from orchestrator.app.main import app
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                resp = await client.post("/chat/stream", json={
                    "messages": [{"role": "user", "content": "sync garmin"}],
                })

    assert resp.status_code == 200
    events = parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "RunStarted"
    assert types[-1] == "RunFinished"
    content_events = [e for e in events if e["type"] == "TextMessageContent"]
    full_text = "".join(e["delta"] for e in content_events)
    assert "5" in full_text  # synced count


@pytest.mark.asyncio
async def test_agents_endpoint_returns_full_info():
    """GET /agents returns name, url, online, capabilities, tasks_today."""
    with patch("orchestrator.app.main.get_tasks_today", new=AsyncMock(return_value=3)):
        with patch("orchestrator.app.main.check_agent_health", new=AsyncMock(return_value=True)):
            with patch("orchestrator.app.registry._registry", {
                "sleep": {
                    "url": "http://agent-sleep:8001",
                    "card": {"name": "sleep-agent", "capabilities": {"streaming": True, "pushNotifications": True}},
                    "online": True,
                }
            }):
                from orchestrator.app.main import app
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    assert len(agents) == 1
    assert agents[0]["name"] == "sleep"
    assert agents[0]["online"] is True
    assert "capabilities" in agents[0]
    assert "tasks_today" in agents[0]
