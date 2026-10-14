"""The chat tool syncs the asking user and reports per service, without provider error texts."""

import os

os.environ.setdefault("AUTH_MODE", "dev")

from unittest.mock import AsyncMock, MagicMock, patch

USER = "eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"


async def test_sync_tool_posts_the_user_and_summarises():
    from orchestrator.app.health_agent import _sync_health_data_for

    response = MagicMock()
    response.raise_for_status = MagicMock()
    response.json.return_value = {
        "user_id": USER,
        "results": [
            {"service": "garmin", "status": "ok", "written": 3, "unchanged": 10},
            {"service": "yazio", "status": "auth_failed", "written": 0, "unchanged": 0},
        ],
    }
    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(return_value=response)
    with patch("httpx.AsyncClient", return_value=client):
        text = await _sync_health_data_for(USER)
    url, kwargs = client.post.call_args.args[0], client.post.call_args.kwargs
    assert url.endswith("/sync/user") and kwargs["json"] == {"user_id": USER}
    assert (
        text
        == "Sync: garmin ok (3 new or updated); yazio auth_failed — reconnect it in Integrations."
    )


async def test_sync_tool_failure_is_generic():
    from orchestrator.app.health_agent import _sync_health_data_for

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    client.post = AsyncMock(side_effect=RuntimeError("http://sync-service:8080 secret"))
    with patch("httpx.AsyncClient", return_value=client):
        assert await _sync_health_data_for(USER) == "Sync failed: the sync service is unavailable."


async def test_sync_tool_uses_injected_user_state():
    from orchestrator.app.health_agent import sync_health_data

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    response = MagicMock()
    response.json.return_value = {"results": []}
    client.post = AsyncMock(return_value=response)
    with patch("httpx.AsyncClient", return_value=client):
        result = await sync_health_data.ainvoke({"state": {"messages": [], "userId": USER}})
    assert result == "Sync: no integrations connected."
    assert client.post.call_args.kwargs["json"] == {"user_id": USER}


async def test_sync_tool_rejects_missing_user_before_contacting_service():
    from orchestrator.app.health_agent import sync_health_data

    with patch("httpx.AsyncClient") as client:
        assert (
            await sync_health_data.ainvoke({"state": {"messages": []}})
            == "Sync failed: unknown user."
        )
    client.assert_not_called()
