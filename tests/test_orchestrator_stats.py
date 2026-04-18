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
async def test_agents_endpoint_returns_skills():
    """GET /agents returns name, url, online, skills[{id,name}], tasks_today."""
    with patch("orchestrator.app.main.get_tasks_today", new=AsyncMock(return_value=3)):
        with patch("orchestrator.app.main.check_agent_health", new=AsyncMock(return_value=True)):
            with patch("orchestrator.app.registry._registry", {
                "sleep": {
                    "url": "http://agent-sleep:8001",
                    "card": {
                        "name": "sleep-agent",
                        "description": "Sleep tracker",
                        "capabilities": {"streaming": True, "pushNotifications": True},
                        "skills": [
                            {"id": "log_sleep", "name": "Log sleep", "description": "..."},
                            {"id": "analyze_sleep", "name": "Analyze sleep"},
                        ],
                    },
                    "online": True,
                }
            }):
                from orchestrator.app.main import app
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    assert len(agents) == 1
    agent = agents[0]
    assert agent["name"] == "sleep"
    assert agent["online"] is True
    assert agent["tasks_today"] == 3
    assert "capabilities" not in agent
    assert agent["skills"] == [
        {"id": "log_sleep", "name": "Log sleep"},
        {"id": "analyze_sleep", "name": "Analyze sleep"},
    ]


@pytest.mark.asyncio
async def test_agents_endpoint_handles_missing_skills():
    """Agents with no skills field return skills: []."""
    with patch("orchestrator.app.main.get_tasks_today", new=AsyncMock(return_value=0)):
        with patch("orchestrator.app.main.check_agent_health", new=AsyncMock(return_value=True)):
            with patch("orchestrator.app.registry._registry", {
                "mystery": {
                    "url": "http://agent-mystery:9999",
                    "card": {"name": "mystery-agent"},
                    "online": True,
                }
            }):
                from orchestrator.app.main import app
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.get("/agents")
    assert resp.status_code == 200
    agents = resp.json()["agents"]
    assert agents[0]["skills"] == []
    assert agents[0]["description"] == ""
