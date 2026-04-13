import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


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
async def test_agents_endpoint_returns_full_info():
    """GET /agents returns name, url, online, capabilities, tasks_today."""
    with patch("orchestrator.app.db.get_tasks_today", new=AsyncMock(return_value=3)):
        with patch("orchestrator.app.registry._registry", {
            "sleep": {
                "url": "http://agent-sleep:8001",
                "card": {"name": "sleep-agent", "capabilities": ["analyze_sleep"]},
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
