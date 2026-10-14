"""POST /sync/trigger asks the sync service to sync the authenticated user only."""

from __future__ import annotations

import asyncio
import os

os.environ.setdefault("AUTH_MODE", "dev")

from unittest.mock import AsyncMock, MagicMock, patch

from httpx import ASGITransport, AsyncClient

USER = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"
AUTH_HEADER = {"X-User-Id": USER}


async def test_sync_trigger_posts_the_user_to_sync_user(monkeypatch):
    from orchestrator.app import auth
    from orchestrator.app.main import app

    monkeypatch.setattr(auth, "AUTH_MODE", "dev")

    posted: list[tuple[str, dict]] = []

    async def fake_post(url, **kwargs):
        posted.append((url, kwargs.get("json")))
        response = MagicMock()
        response.status_code = 200
        return response

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=fake_post)

    with patch("httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post("/sync/trigger", headers=AUTH_HEADER)
        await asyncio.sleep(0.1)  # let the background task run

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    from orchestrator.app.main import _SYNC_SERVICE_BASE

    assert posted == [(f"{_SYNC_SERVICE_BASE}/sync/user", {"user_id": USER})]
