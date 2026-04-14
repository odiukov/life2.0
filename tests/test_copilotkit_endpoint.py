import pytest
import httpx
from orchestrator.app.main import app


@pytest.mark.asyncio
async def test_copilotkit_endpoint_is_registered():
    """POST /copilotkit should exist (not 404)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post("/copilotkit", json={})
    assert response.status_code != 404
