"""POST /sync/trigger should fire a single /sync/all call to the sync service."""
from __future__ import annotations

import os
os.environ.setdefault("AUTH_MODE", "dev")
os.environ.setdefault("VAULT_BACKEND", "dev")

import asyncio
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import ASGITransport, AsyncClient

AUTH_HEADER = {"X-User-Id": "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"}


async def test_sync_trigger_calls_sync_all():
    from orchestrator.app.main import app

    posted_urls: list[str] = []

    async def fake_post(url, **_kwargs):
        posted_urls.append(url)
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        return mock_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=fake_post)

    with patch("httpx.AsyncClient", return_value=mock_client):
        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as c:
            resp = await c.post("/sync/trigger", headers=AUTH_HEADER)
        # Let the background task run before checking assertions
        await asyncio.sleep(0.1)

    assert resp.status_code == 200
    assert resp.json() == {"ok": True}
    # Must call /sync/all — not the old two-call pattern
    sync_all_calls = [u for u in posted_urls if u.endswith("/sync/all")]
    assert len(sync_all_calls) == 1, f"Expected 1 /sync/all call, got: {posted_urls}"
    # Must NOT call /sync or /sync/nutrition separately
    assert not any(u.endswith("/sync") and not u.endswith("/sync/all") for u in posted_urls)
    assert not any(u.endswith("/sync/nutrition") for u in posted_urls)
