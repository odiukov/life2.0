import types

import pytest
from httpx import ASGITransport, AsyncClient


@pytest.mark.asyncio
async def test_chat_stream_emits_runstarted_and_finished(monkeypatch):
    async def fake_astream(state, config=None):
        yield {"agent": {"messages": [types.SimpleNamespace(content="hello")]}}

    from orchestrator.app import main as main_mod
    monkeypatch.setattr(main_mod._graph, "astream", fake_astream)

    async with AsyncClient(transport=ASGITransport(app=main_mod.app), base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        ) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    assert b"RunStarted" in body
    assert b"hello" in body
    assert b"RunFinished" in body


@pytest.mark.asyncio
async def test_chat_stream_no_user_message_returns_400():
    from orchestrator.app.main import app
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat/stream", json={"messages": []})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_stream_content_type_is_event_stream(monkeypatch):
    async def fake_astream(state, config=None):
        if False:
            yield {}
        return

    from orchestrator.app import main as main_mod
    monkeypatch.setattr(main_mod._graph, "astream", fake_astream)

    async with AsyncClient(transport=ASGITransport(app=main_mod.app), base_url="http://test") as client:
        resp = await client.post(
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_chat_stream_surfaces_graph_exception(monkeypatch):
    async def fake_astream(state, config=None):
        yield {"agent": {"messages": [types.SimpleNamespace(content="partial")]}}
        raise RuntimeError("boom")

    from orchestrator.app import main as main_mod
    monkeypatch.setattr(main_mod._graph, "astream", fake_astream)

    async with AsyncClient(transport=ASGITransport(app=main_mod.app), base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        ) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    assert b"Error: boom" in body
    assert b"RunFinished" in body


@pytest.mark.asyncio
async def test_chat_stream_uses_provided_thread_and_run_ids(monkeypatch):
    async def fake_astream(state, config=None):
        if False:
            yield {}
        return

    from orchestrator.app import main as main_mod
    monkeypatch.setattr(main_mod._graph, "astream", fake_astream)

    async with AsyncClient(transport=ASGITransport(app=main_mod.app), base_url="http://test") as client:
        async with client.stream(
            "POST",
            "/chat/stream",
            json={
                "threadId": "thread-xyz",
                "runId": "run-abc",
                "messages": [{"role": "user", "content": "hi"}],
            },
        ) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    assert b"thread-xyz" in body
    assert b"run-abc" in body
