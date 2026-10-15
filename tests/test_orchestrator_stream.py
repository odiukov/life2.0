import types
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient
from langchain_core.messages import AIMessage, ToolMessage


@pytest.fixture(autouse=True)
def authenticated_user():
    from legacy_orchestrator.app.auth import current_user
    from legacy_orchestrator.app.main import app

    async def user():
        return UUID("11111111-1111-1111-1111-111111111111")

    previous = app.dependency_overrides.copy()
    app.dependency_overrides[current_user] = user
    try:
        yield
    finally:
        app.dependency_overrides.clear()
        app.dependency_overrides.update(previous)


@pytest.mark.asyncio
async def test_chat_stream_emits_runstarted_and_finished(monkeypatch):
    async def fake_astream(state, config=None):
        yield {"agent": {"messages": [AIMessage(content="hello")]}}

    from legacy_orchestrator.app import main as main_mod

    monkeypatch.setattr(main_mod, "_graph", types.SimpleNamespace(astream=fake_astream))

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app), base_url="http://test"
    ) as client:
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
    from legacy_orchestrator.app.main import app

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        resp = await client.post("/chat/stream", json={"messages": []})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_chat_stream_content_type_is_event_stream(monkeypatch):
    async def fake_astream(state, config=None):
        if False:
            yield {}
        return

    from legacy_orchestrator.app import main as main_mod

    monkeypatch.setattr(main_mod, "_graph", types.SimpleNamespace(astream=fake_astream))

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app), base_url="http://test"
    ) as client:
        resp = await client.post(
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        )
    assert resp.status_code == 200
    assert "text/event-stream" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_chat_stream_surfaces_graph_exception(monkeypatch):
    async def fake_astream(state, config=None):
        yield {"agent": {"messages": [AIMessage(content="partial")]}}
        raise RuntimeError("boom")

    from legacy_orchestrator.app import main as main_mod

    monkeypatch.setattr(main_mod, "_graph", types.SimpleNamespace(astream=fake_astream))

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app), base_url="http://test"
    ) as client:
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
async def test_chat_stream_skips_toolmessages_and_tool_call_aimessages(monkeypatch):
    """Regression: only final AIMessage content is streamed. Otherwise tool output +
    final reply get concatenated client-side, producing duplicated text (seen when
    sleep-agent's analysis is echoed verbatim by the ReAct agent)."""

    async def fake_astream(state, config=None):
        yield {
            "agent": {
                "messages": [
                    AIMessage(
                        content="", tool_calls=[{"id": "c1", "name": "ask_sleep_agent", "args": {}}]
                    )
                ]
            }
        }
        yield {
            "tools": {"messages": [ToolMessage(content="sleep analysis text", tool_call_id="c1")]}
        }
        yield {"agent": {"messages": [AIMessage(content="final answer")]}}

    from legacy_orchestrator.app import main as main_mod

    monkeypatch.setattr(main_mod, "_graph", types.SimpleNamespace(astream=fake_astream))

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app), base_url="http://test"
    ) as client:
        async with client.stream(
            "POST",
            "/chat/stream",
            json={"messages": [{"role": "user", "content": "hi"}]},
        ) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    assert b"final answer" in body
    assert b"sleep analysis text" not in body


@pytest.mark.asyncio
async def test_chat_stream_resets_thread_on_invalid_chat_history(monkeypatch):
    """After an interrupted run, the checkpoint may hold AIMessage tool_calls without
    matching ToolMessages. Subsequent calls must wipe the thread and retry once rather
    than failing the user's next question permanently."""
    deleted: list[str] = []

    class FakeSaver:
        async def adelete_thread(self, tid):
            deleted.append(tid)

    call = {"n": 0}

    async def fake_astream(state, config=None):
        call["n"] += 1
        if call["n"] == 1:
            raise ValueError("Found AIMessages with tool_calls ... [INVALID_CHAT_HISTORY]")
        yield {"agent": {"messages": [AIMessage(content="recovered")]}}

    from legacy_orchestrator.app import main as main_mod

    monkeypatch.setattr(main_mod, "_graph", types.SimpleNamespace(astream=fake_astream))
    monkeypatch.setattr(main_mod, "_saver", FakeSaver())

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app), base_url="http://test"
    ) as client:
        async with client.stream(
            "POST",
            "/chat/stream",
            json={"threadId": "tg-123", "messages": [{"role": "user", "content": "hi"}]},
        ) as resp:
            body = b""
            async for chunk in resp.aiter_bytes():
                body += chunk

    assert deleted == ["tg-123"]
    assert b"recovered" in body
    assert b"INVALID_CHAT_HISTORY" not in body  # error message is swallowed, not surfaced


@pytest.mark.asyncio
async def test_chat_stream_uses_provided_thread_and_run_ids(monkeypatch):
    async def fake_astream(state, config=None):
        if False:
            yield {}
        return

    from legacy_orchestrator.app import main as main_mod

    monkeypatch.setattr(main_mod, "_graph", types.SimpleNamespace(astream=fake_astream))

    async with AsyncClient(
        transport=ASGITransport(app=main_mod.app), base_url="http://test"
    ) as client:
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


@pytest.mark.asyncio
async def test_chat_consent_queries_authenticated_uuid_and_caches_per_user(monkeypatch):
    from opentelemetry import baggage
    from legacy_orchestrator.app import consent_resolver, main
    from legacy_orchestrator.app.auth import current_user

    first = UUID("11111111-1111-1111-1111-111111111111")
    second = UUID("22222222-2222-2222-2222-222222222222")
    queries, captured = [], []

    class Pool:
        async def fetchval(self, query, user_id):
            queries.append(user_id)
            return user_id == first

    async def pool():
        return Pool()

    async def graph(*args):
        captured.append(baggage.get_baggage("telemetry.bodies_ok"))
        yield "sleep", [], "hello"

    monkeypatch.setenv("TELEMETRY_CAPTURE_BODIES", "consented")
    monkeypatch.setenv("LANGFUSE_DEFAULT_USER_ID", "owner")
    monkeypatch.setattr(consent_resolver, "get_pool", pool)
    monkeypatch.setattr(main, "_run_graph_with_routing", graph)
    consent_resolver.clear_cache()
    try:
        async with AsyncClient(
            transport=ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            for actor in (first, second, first):

                async def user():
                    return actor

                main.app.dependency_overrides[current_user] = user
                response = await client.post(
                    "/chat/stream", json={"messages": [{"role": "user", "content": "hi"}]}
                )
                assert response.status_code == 200
        assert queries == [first, second]
        assert captured == ["1", "0", "1"]
        assert set(consent_resolver._CACHE) == {first, second}
    finally:
        consent_resolver.clear_cache()


@pytest.mark.asyncio
async def test_chat_consent_failure_denies_capture_and_logs_type_only(monkeypatch, caplog):
    from opentelemetry import baggage
    from legacy_orchestrator.app import consent_resolver, main

    captured = []

    async def failed_lookup(user_id):
        raise RuntimeError("private consent payload")

    async def graph(*args):
        captured.append(baggage.get_baggage("telemetry.bodies_ok"))
        yield "sleep", [], "hello"

    monkeypatch.setenv("TELEMETRY_CAPTURE_BODIES", "consented")
    monkeypatch.setattr(consent_resolver, "is_consented", failed_lookup)
    monkeypatch.setattr(main, "_run_graph_with_routing", graph)
    with caplog.at_level("WARNING", logger=main.__name__):
        async with AsyncClient(
            transport=ASGITransport(app=main.app), base_url="http://test"
        ) as client:
            response = await client.post(
                "/chat/stream", json={"messages": [{"role": "user", "content": "hi"}]}
            )
    assert response.status_code == 200
    assert captured == ["0"]
    assert "private consent payload" not in caplog.text
    assert "consent_lookup_failed error_type=RuntimeError" in caplog.text
