import pytest
import json
from unittest.mock import AsyncMock, patch, MagicMock
from httpx import AsyncClient, ASGITransport


def parse_sse(raw: str) -> list[dict]:
    """Parse text/event-stream response into list of event dicts."""
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


@pytest.mark.asyncio
async def test_chat_stream_emits_agui_events():
    """POST /chat/stream emits RunStarted → TextMessageContent → RunFinished."""
    mock_resp = MagicMock()
    mock_resp.status_code = 200
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json = MagicMock(return_value={"status": "completed", "output": "Sleep better tonight."})

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.post = AsyncMock(return_value=mock_resp)

    with patch("orchestrator.app.main.get_agent_url", return_value="http://agent-sleep:8001"):
        with patch("orchestrator.app.main.classify_intent", return_value="sleep"):
            with patch("httpx.AsyncClient", return_value=mock_client):
                from orchestrator.app.main import app
                async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                    resp = await client.post("/chat/stream", json={
                        "threadId": "t1",
                        "runId": "r1",
                        "messages": [{"role": "user", "content": "How was my sleep?"}],
                        "actions": [],
                    })

    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]
    events = parse_sse(resp.text)
    types = [e["type"] for e in events]
    assert types[0] == "RunStarted"
    assert types[-1] == "RunFinished"
    assert "TextMessageStart" in types
    assert "TextMessageEnd" in types
    content_events = [e for e in events if e["type"] == "TextMessageContent"]
    assert len(content_events) > 0
    full_text = "".join(e["delta"] for e in content_events)
    assert "Sleep better tonight." in full_text


@pytest.mark.asyncio
async def test_chat_stream_no_user_message_returns_400():
    from orchestrator.app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat/stream", json={
            "messages": [],
        })
    assert resp.status_code == 400
