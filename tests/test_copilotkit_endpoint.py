import sys
from unittest.mock import MagicMock

# langgraph 0.5+ removed langgraph.graph.graph; stub it so copilotkit 0.1.39 imports cleanly.
if "langgraph.graph.graph" not in sys.modules:
    _mock_gg = MagicMock()
    _mock_gg.CompiledGraph = MagicMock
    sys.modules["langgraph.graph.graph"] = _mock_gg

import pytest
import httpx
from unittest.mock import AsyncMock, patch
from orchestrator.app.main import (
    app,
    _call_health_agent_handler,
    _run_sync_handler,
    _run_briefing_handler,
)


@pytest.mark.asyncio
async def test_copilotkit_endpoint_is_registered():
    """POST /copilotkit should exist (not 404)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/copilotkit", json={})
    assert response.status_code != 404


@pytest.mark.asyncio
async def test_call_health_agent_handler_unavailable_agent():
    """Returns a soft-error string when the agent is not registered."""
    with patch("orchestrator.app.main.get_agent_url", return_value=None):
        result = await _call_health_agent_handler(message="hello", agent="sleep")
    assert "unavailable" in result.lower()


@pytest.mark.asyncio
async def test_run_sync_handler_returns_summary_on_success():
    """Returns a sync summary string on successful sync."""
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"synced": 5, "skipped": 2, "errors": []}

    with patch("httpx.AsyncClient") as mock_client_cls:
        mock_client = AsyncMock()
        mock_client.__aenter__ = AsyncMock(return_value=mock_client)
        mock_client.__aexit__ = AsyncMock(return_value=False)
        mock_client.post = AsyncMock(return_value=mock_response)
        mock_client_cls.return_value = mock_client

        result = await _run_sync_handler()

    assert "5" in result and "2" in result


@pytest.mark.asyncio
async def test_run_briefing_handler_returns_string_on_failure():
    """Returns a soft-error string when run_briefing raises."""
    with patch("orchestrator.app.main.run_briefing", side_effect=RuntimeError("telegram error")):
        result = await _run_briefing_handler()
    assert "failed" in result.lower() or "error" in result.lower()
