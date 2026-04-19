import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

import httpx

from telegram_bot.app.client import ask_orchestrator


def _sse_lines(events: list[dict]) -> list[str]:
    return [f"data: {json.dumps(e)}" for e in events]


def _build_stream_client(lines: list[str] | None = None, *, exc: Exception | None = None, raise_status: Exception | None = None):
    stream_ctx = AsyncMock()
    stream_ctx.__aenter__ = AsyncMock(return_value=stream_ctx)
    stream_ctx.__aexit__ = AsyncMock(return_value=False)
    if raise_status is not None:
        stream_ctx.raise_for_status = MagicMock(side_effect=raise_status)
    else:
        stream_ctx.raise_for_status = MagicMock()

    async def aiter_lines():
        for line in lines or []:
            yield line

    stream_ctx.aiter_lines = aiter_lines

    client = AsyncMock()
    client.__aenter__ = AsyncMock(return_value=client)
    client.__aexit__ = AsyncMock(return_value=False)
    if exc is not None:
        client.stream = MagicMock(side_effect=exc)
    else:
        client.stream = MagicMock(return_value=stream_ctx)
    return client


@pytest.mark.asyncio
async def test_ask_orchestrator_accumulates_text_deltas():
    events = [
        {"type": "RunStarted", "threadId": "t", "runId": "r"},
        {"type": "TextMessageStart", "messageId": "m", "role": "assistant"},
        {"type": "TextMessageContent", "messageId": "m", "delta": "You slept "},
        {"type": "TextMessageContent", "messageId": "m", "delta": "well."},
        {"type": "TextMessageEnd", "messageId": "m"},
        {"type": "RunFinished", "threadId": "t", "runId": "r"},
    ]
    client = _build_stream_client(_sse_lines(events))
    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=client):
        result = await ask_orchestrator("I slept 7 hours", "tg-1-2026-04-19-v0")

    args, kwargs = client.stream.call_args
    assert args[0] == "POST"
    assert args[1] == "http://orchestrator:8000/chat/stream"
    assert kwargs["json"] == {
        "threadId": "tg-1-2026-04-19-v0",
        "messages": [{"role": "user", "content": "I slept 7 hours"}],
    }
    assert result == "You slept well."


@pytest.mark.asyncio
async def test_ask_orchestrator_empty_stream_returns_placeholder():
    client = _build_stream_client([])
    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=client):
        result = await ask_orchestrator("test", "tg-1-2026-04-19-v0")
    assert result == "(empty response)"


@pytest.mark.asyncio
async def test_ask_orchestrator_on_request_error_returns_friendly_message():
    client = _build_stream_client(exc=httpx.RequestError("connection refused"))
    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=client):
        result = await ask_orchestrator("test", "tg-1-2026-04-19-v0")
    assert "unavailable" in result.lower()


@pytest.mark.asyncio
async def test_ask_orchestrator_on_http_status_error_returns_friendly_message():
    mock_request = MagicMock()
    mock_resp = MagicMock()
    mock_resp.status_code = 500
    mock_resp.text = "Internal Server Error"
    status_err = httpx.HTTPStatusError("500", request=mock_request, response=mock_resp)
    client = _build_stream_client([], raise_status=status_err)
    with patch("telegram_bot.app.client.httpx.AsyncClient", return_value=client):
        result = await ask_orchestrator("test", "tg-1-2026-04-19-v0")
    assert "500" in result
