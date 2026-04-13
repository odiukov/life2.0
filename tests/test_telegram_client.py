import pytest
from unittest.mock import AsyncMock, MagicMock, patch


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
        from telegram_bot.app.client import ask_orchestrator
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
        from telegram_bot.app.client import ask_orchestrator
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
        from telegram_bot.app.client import ask_orchestrator
        result = await ask_orchestrator("test")

    assert "unavailable" in result.lower()
