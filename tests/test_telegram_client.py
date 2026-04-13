import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from telegram_bot.app.client import ask_orchestrator


@pytest.mark.asyncio
async def test_ask_orchestrator_returns_output():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"status": "completed", "output": "You slept well."})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=mock_client):
        result = await ask_orchestrator("I slept 7 hours")

    mock_client.post.assert_called_once_with(
        "http://orchestrator:8000/chat",
        json={"message": "I slept 7 hours", "params": {}},
    )
    assert result == "You slept well."


@pytest.mark.asyncio
async def test_ask_orchestrator_returns_error_output():
    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json = MagicMock(return_value={"status": "error", "output": "Agent unavailable"})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=mock_client):
        result = await ask_orchestrator("test")

    assert result == "Agent unavailable"


@pytest.mark.asyncio
async def test_ask_orchestrator_on_http_error_returns_friendly_message():
    import httpx

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(side_effect=httpx.RequestError("connection refused"))

    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=mock_client):
        result = await ask_orchestrator("test")

    assert "unavailable" in result.lower()


@pytest.mark.asyncio
async def test_ask_orchestrator_on_http_status_error_returns_friendly_message():
    import httpx

    mock_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock(
        side_effect=httpx.HTTPStatusError("500", request=mock_request, response=mock_resp)
    )

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.post = AsyncMock(return_value=mock_response)

    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=mock_client):
        result = await ask_orchestrator("test")

    assert "500" in result
