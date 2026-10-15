from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from opentelemetry import baggage
from orchestrator.adapters.http import build_router
from orchestrator.domain.attachments import MAX_TOTAL


@pytest.mark.parametrize("consented", [False, True])
async def test_stream_carries_consent_and_cleans_context(consented, monkeypatch):
    user = uuid4()
    seen = []
    tracer = MagicMock()
    monkeypatch.setattr("orchestrator.adapters.http.trace.get_tracer", lambda _: tracer)
    task = uuid4()

    async def authenticate():
        return user

    async def events():
        seen.append(baggage.get_baggage("telemetry.bodies_ok"))
        yield {"type": "RunFinished"}

    post = SimpleNamespace(
        start=AsyncMock(return_value=SimpleNamespace(events=events, aclose=AsyncMock()))
    )
    consent = SimpleNamespace(bodies_ok=AsyncMock(return_value=consented))
    app = FastAPI()
    app.include_router(build_router(AsyncMock(), post, AsyncMock(), authenticate, consent=consent))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(f"/tasks/{task}/messages", data={"text": "hello"})
    assert response.status_code == 200
    assert "RunFinished" in response.text
    assert seen == ["1" if consented else "0"]
    assert baggage.get_baggage("telemetry.bodies_ok") is None
    consent.bodies_ok.assert_awaited_once_with(user)
    tracer.start_as_current_span.assert_called_once_with(
        "chat.run", attributes={"langfuse.session.id": str(task), "user.id": str(user)}
    )
    assert post.start.return_value.aclose.await_count >= 1


async def test_oversized_envelope_is_rejected_before_start():
    post = SimpleNamespace(start=AsyncMock())

    async def authenticate():
        return uuid4()

    app = FastAPI()
    app.include_router(build_router(AsyncMock(), post, AsyncMock(), authenticate))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/tasks/{uuid4()}/messages",
            content=b"x",
            headers={"content-length": str(MAX_TOTAL + 1024 * 1024 + 1)},
        )
    assert response.status_code == 413
    post.start.assert_not_awaited()


async def test_chunked_upload_is_capped_before_parsing_completes():
    post = SimpleNamespace(start=AsyncMock())

    async def authenticate():
        return uuid4()

    async def body():
        yield b'--boundary\r\nContent-Disposition: form-data; name="attachments"; filename="large.pdf"\r\nContent-Type: application/pdf\r\n\r\n'
        for _ in range((MAX_TOTAL // 1024) + 1026):
            yield b"x" * 1024

    app = FastAPI()
    app.include_router(build_router(AsyncMock(), post, AsyncMock(), authenticate))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/tasks/{uuid4()}/messages",
            content=body(),
            headers={"content-type": "multipart/form-data; boundary=boundary"},
        )
    assert response.status_code == 413
    post.start.assert_not_awaited()


async def test_attachment_limit_is_checked_after_multipart_parsing(monkeypatch):
    monkeypatch.setattr("orchestrator.adapters.http.MAX_TOTAL", 10)
    post = SimpleNamespace(start=AsyncMock())

    async def authenticate():
        return uuid4()

    app = FastAPI()
    app.include_router(build_router(AsyncMock(), post, AsyncMock(), authenticate))
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app), base_url="http://test"
    ) as client:
        response = await client.post(
            f"/tasks/{uuid4()}/messages",
            files=[("attachments", ("a.pdf", b"x" * 11, "application/pdf"))],
        )
    assert response.status_code == 413
    post.start.assert_not_awaited()


async def test_http_iterator_close_finishes_events_before_releasing_run():
    order = []

    async def events():
        try:
            yield {"type": "TextMessageContent", "delta": "Answer"}
        finally:
            order.append("persisted")

    async def close():
        order.append("released")

    post = SimpleNamespace(
        start=AsyncMock(return_value=SimpleNamespace(events=events, aclose=close))
    )
    router = build_router(AsyncMock(), post, AsyncMock(), AsyncMock())
    route = next(r for r in router.routes if r.path.endswith("/messages"))
    response = await route.endpoint(
        task_id=uuid4(), text="hello", timezone=None, attachments=[], user=uuid4()
    )
    await anext(response.body_iterator)
    await response.body_iterator.aclose()
    assert order == ["persisted", "released"]
