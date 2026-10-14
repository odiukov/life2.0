import asyncio

import httpx
import pytest
from nutrition.adapters.sync import HttpNutritionSync
from structlog.testing import capture_logs


async def test_posts_to_the_sync_service_and_leaves_injected_client_open() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await HttpNutritionSync("http://sync-service:8080/", timeout_s=1.5, client=client).refresh()
        assert not client.is_closed
    assert [(r.method, str(r.url)) for r in seen] == [
        ("POST", "http://sync-service:8080/sync/nutrition")
    ]
    assert seen[0].extensions["timeout"] == {"connect": 1.5, "read": 1.5, "write": 1.5, "pool": 1.5}


async def test_missing_url_does_not_make_a_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with capture_logs() as logs:
            await HttpNutritionSync(None, client=client).refresh()
    assert seen == []
    assert logs == []


@pytest.mark.parametrize("failure", ["connect", "phase_timeout", "http_status"])
async def test_failures_are_best_effort_and_logs_contain_only_error_type(failure: str) -> None:
    secret = "private-meal-and-token"

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "connect":
            raise httpx.ConnectError(secret, request=request)
        if failure == "phase_timeout":
            raise httpx.ReadTimeout(secret, request=request)
        return httpx.Response(503, text=secret)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with capture_logs() as logs:
            await HttpNutritionSync(f"http://sync-service:8080/{secret}", client=client).refresh()
    assert len(logs) == 1
    assert (
        logs[0]["error_type"]
        == {
            "connect": "ConnectError",
            "phase_timeout": "ReadTimeout",
            "http_status": "HTTPStatusError",
        }[failure]
    )
    assert logs[0]["log_level"] in {"info", "warning", "error"}
    assert set(logs[0]) == {"event", "error_type", "log_level"}
    assert secret not in str(logs)
    assert "http://" not in str(logs)


async def test_complete_refresh_has_a_deadline_even_when_transport_ignores_phase_timeout() -> None:
    started, cancelled = asyncio.Event(), asyncio.Event()

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            cancelled.set()
            raise
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with capture_logs() as logs:
            await asyncio.wait_for(
                HttpNutritionSync(
                    "http://sync-service:8080", timeout_s=0.02, client=client
                ).refresh(),
                timeout=0.5,
            )
    assert started.is_set()
    assert cancelled.is_set()
    assert logs == [
        {"event": "nutrition_sync_failed", "error_type": "TimeoutError", "log_level": "warning"}
    ]


async def test_deadline_includes_owned_client_cleanup(monkeypatch: pytest.MonkeyPatch) -> None:
    closing, cancelled = asyncio.Event(), asyncio.Event()
    real_client = httpx.AsyncClient
    clients: list[httpx.AsyncClient] = []

    class SlowClosingTransport(httpx.MockTransport):
        async def aclose(self) -> None:
            closing.set()
            try:
                await asyncio.sleep(1)
            except asyncio.CancelledError:
                cancelled.set()
                raise

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200)

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        client = real_client(transport=SlowClosingTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    with capture_logs() as logs:
        await asyncio.wait_for(
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.02).refresh(), timeout=0.5
        )
    assert closing.is_set()
    assert cancelled.is_set()
    assert clients[0].is_closed
    assert logs[0]["error_type"] == "TimeoutError"


async def test_caller_cancellation_propagates() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with capture_logs() as logs, pytest.raises(asyncio.CancelledError):
            await HttpNutritionSync("http://sync-service:8080", client=client).refresh()
    assert logs == []


async def test_request_timeout_still_bounds_subsequent_owned_client_cleanup(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    request_cancelled, closing, cleanup_cancelled = (
        asyncio.Event(),
        asyncio.Event(),
        asyncio.Event(),
    )
    clients: list[httpx.AsyncClient] = []
    real_client = httpx.AsyncClient

    async def handler(request: httpx.Request) -> httpx.Response:
        try:
            await asyncio.sleep(1)
        except asyncio.CancelledError:
            request_cancelled.set()
            raise
        return httpx.Response(200)

    class SlowClosingTransport(httpx.MockTransport):
        async def aclose(self) -> None:
            closing.set()
            try:
                await asyncio.sleep(0.15)
            except asyncio.CancelledError:
                cleanup_cancelled.set()
                raise

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        client = real_client(transport=SlowClosingTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    with capture_logs() as logs:
        await asyncio.wait_for(
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.02).refresh(), timeout=0.1
        )
    assert request_cancelled.is_set()
    assert closing.is_set()
    assert cleanup_cancelled.is_set()
    assert clients[0].is_closed
    assert logs == [
        {"event": "nutrition_sync_failed", "error_type": "TimeoutError", "log_level": "warning"}
    ]


async def test_caller_cancellation_is_not_replaced_by_owned_cleanup_deadline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    started, closing, cleanup_cancelled = asyncio.Event(), asyncio.Event(), asyncio.Event()
    real_client = httpx.AsyncClient
    clients: list[httpx.AsyncClient] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(1)
        return httpx.Response(200)

    class SlowClosingTransport(httpx.MockTransport):
        async def aclose(self) -> None:
            closing.set()
            try:
                await asyncio.sleep(0.15)
            except asyncio.CancelledError:
                cleanup_cancelled.set()
                raise

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        client = real_client(transport=SlowClosingTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    with capture_logs() as logs:
        task = asyncio.create_task(
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.02).refresh()
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.1)
    assert task.done()
    assert closing.is_set()
    assert cleanup_cancelled.is_set()
    assert clients[0].is_closed
    assert logs == []


@pytest.mark.parametrize("failure", ["http", "programming"])
async def test_owned_cleanup_failure_cannot_swallow_caller_cancellation(
    monkeypatch: pytest.MonkeyPatch, failure: str
) -> None:
    started = asyncio.Event()
    real_client = httpx.AsyncClient
    clients: list[httpx.AsyncClient] = []

    async def handler(request: httpx.Request) -> httpx.Response:
        started.set()
        await asyncio.sleep(1)
        return httpx.Response(200)

    class FailingCleanupTransport(httpx.MockTransport):
        async def aclose(self) -> None:
            if failure == "http":
                raise httpx.ReadTimeout("private cleanup detail")
            raise RuntimeError("private cleanup detail")

    def client_factory(**kwargs: object) -> httpx.AsyncClient:
        client = real_client(transport=FailingCleanupTransport(handler), **kwargs)
        clients.append(client)
        return client

    monkeypatch.setattr(httpx, "AsyncClient", client_factory)
    with capture_logs() as logs:
        task = asyncio.create_task(
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.5).refresh()
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.1)
    assert task.done()
    assert clients[0].is_closed
    assert logs == []
