# tests/test_orchestrator_stream.py
import json
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


def parse_sse(raw: str) -> list[dict]:
    events = []
    for line in raw.splitlines():
        if line.startswith("data: "):
            events.append(json.loads(line[6:]))
    return events


def _make_stream_mock(sse_lines: list[str]):
    """Build a mock for httpx streaming context manager."""
    mock_resp = MagicMock()
    mock_resp.__aenter__ = AsyncMock(return_value=mock_resp)
    mock_resp.__aexit__ = AsyncMock(return_value=None)

    async def aiter_lines():
        for line in sse_lines:
            yield line

    mock_resp.aiter_lines = aiter_lines

    mock_client = MagicMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)
    mock_client.stream = MagicMock(return_value=mock_resp)
    return mock_client


@pytest.mark.asyncio
async def test_chat_stream_emits_agui_events():
    """POST /chat/stream emits RunStarted → TextMessageContent → RunFinished."""
    task_id = "test-task-id"
    sse_lines = [
        "event: task-status-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "submitted", "timestamp": ""}})}',
        "",
        "event: task-status-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}})}',
        "",
        "event: task-artifact-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "completed", "timestamp": ""}, "artifacts": [{"name": "analysis", "parts": [{"type": "text", "text": "Sleep better tonight."}]}]})}',
        "",
    ]
    mock_client = _make_stream_mock(sse_lines)

    with patch("orchestrator.app.main.get_agent_url", return_value="http://agent-sleep:8001"):
        with patch("orchestrator.app.main.classify_intent", return_value="sleep"):
            with patch("orchestrator.app.main._build_peer_agents", return_value={}):
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
    assert "TextMessageContent" in types
    full_text = "".join(e.get("delta", "") for e in events if e.get("type") == "TextMessageContent")
    assert "Sleep better tonight." in full_text


@pytest.mark.asyncio
async def test_chat_stream_emits_peer_status_for_workout():
    """Workout stream emits peer status messages before the final answer."""
    task_id = "wk-task"
    sse_lines = [
        "event: task-status-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "submitted", "timestamp": ""}})}',
        "",
        "event: task-status-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}})}',
        "",
        "event: task-artifact-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}, "artifacts": [{"name": "peer_sleep", "parts": [{"type": "text", "text": "slept 7h"}]}]})}',
        "",
        "event: task-artifact-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}, "artifacts": [{"name": "peer_nutrition", "parts": [{"type": "text", "text": "2000 kcal"}]}]})}',
        "",
        "event: task-artifact-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "completed", "timestamp": ""}, "artifacts": [{"name": "analysis", "parts": [{"type": "text", "text": "Grouped analysis."}]}]})}',
        "",
    ]
    mock_client = _make_stream_mock(sse_lines)

    with patch("orchestrator.app.main.get_agent_url", return_value="http://agent-workout:8002"):
        with patch("orchestrator.app.main.classify_intent", return_value="workout"):
            with patch("orchestrator.app.main._build_peer_agents", return_value={}):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    from orchestrator.app.main import app
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        resp = await client.post("/chat/stream", json={
                            "messages": [{"role": "user", "content": "How was my workout?"}],
                        })

    events = parse_sse(resp.text)
    full_text = "".join(e.get("delta", "") for e in events if e.get("type") == "TextMessageContent")
    assert "sleep" in full_text.lower()
    assert "nutrition" in full_text.lower()
    assert "Grouped analysis." in full_text


@pytest.mark.asyncio
async def test_chat_stream_surfaces_agent_failure():
    """Failed agent state surfaces error text to the user instead of silent empty response."""
    task_id = "fail-task"
    sse_lines = [
        "event: task-status-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "working", "timestamp": ""}})}',
        "",
        "event: task-artifact-update",
        f'data: {json.dumps({"id": task_id, "status": {"state": "failed", "timestamp": ""}, "artifacts": [{"name": "error", "parts": [{"type": "text", "text": "Claude unavailable"}]}]})}',
        "",
    ]
    mock_client = _make_stream_mock(sse_lines)

    with patch("orchestrator.app.main.get_agent_url", return_value="http://agent-sleep:8001"):
        with patch("orchestrator.app.main.classify_intent", return_value="sleep"):
            with patch("orchestrator.app.main._build_peer_agents", return_value={}):
                with patch("httpx.AsyncClient", return_value=mock_client):
                    from orchestrator.app.main import app
                    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
                        resp = await client.post("/chat/stream", json={
                            "messages": [{"role": "user", "content": "How was my sleep?"}],
                        })

    events = parse_sse(resp.text)
    full_text = "".join(e.get("delta", "") for e in events if e.get("type") == "TextMessageContent")
    assert "Claude unavailable" in full_text


@pytest.mark.asyncio
async def test_chat_stream_no_user_message_returns_400():
    from orchestrator.app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat/stream", json={"messages": []})
    assert resp.status_code == 400
