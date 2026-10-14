import asyncio
import json
import logging
from collections.abc import Iterator
from uuid import UUID

import httpx
import pytest
import structlog
from nutrition.adapters.sync import HttpNutritionSync
from structlog.testing import capture_logs

USER = UUID("11111111-1111-1111-1111-111111111111")


@pytest.fixture(autouse=True)
def debug_log_capture() -> Iterator[None]:
    config = structlog.get_config()
    structlog.configure(wrapper_class=structlog.make_filtering_bound_logger(logging.DEBUG))
    try:
        yield
    finally:
        structlog.configure(**config)


async def test_posts_to_the_sync_service_and_leaves_injected_client_open() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        await HttpNutritionSync("http://sync-service:8080/", timeout_s=1.5, client=client).refresh(
            USER
        )
        assert not client.is_closed
    assert [(r.method, str(r.url)) for r in seen] == [
        ("POST", "http://sync-service:8080/sync/user")
    ]
    assert json.loads(seen[0].content) == {"user_id": str(USER), "services": ["yazio"]}
    assert seen[0].extensions["timeout"] == {"connect": 1.5, "read": 1.5, "write": 1.5, "pool": 1.5}


async def test_missing_url_does_not_make_a_request() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with capture_logs() as logs:
            await HttpNutritionSync(None, client=client).refresh(USER)
    assert seen == []
    assert logs == []


@pytest.mark.parametrize("failure", ["connect", "phase_timeout", "http_status"])
async def test_failures_log_codes_and_debug_type_without_private_details(failure: str) -> None:
    secret = "private-meal-and-token"

    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "connect":
            raise httpx.ConnectError(secret, request=request)
        if failure == "phase_timeout":
            raise httpx.ReadTimeout(secret, request=request)
        return httpx.Response(503, text=secret)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with capture_logs() as logs:
            await HttpNutritionSync(f"http://sync-service:8080/{secret}", client=client).refresh(
                USER
            )
    assert len(logs) == 2
    assert (
        logs[1]["error_type"]
        == {
            "connect": "ConnectError",
            "phase_timeout": "ReadTimeout",
            "http_status": "HTTPStatusError",
        }[failure]
    )
    assert logs[0]["log_level"] in {"info", "warning", "error"}
    assert set(logs[0]) == {"event", "code", "user_id", "service", "log_level"}
    assert logs[1]["log_level"] == "debug"
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
                ).refresh(USER),
                timeout=0.5,
            )
    assert started.is_set()
    assert cancelled.is_set()
    assert logs == [
        {
            "event": "nutrition_sync_failed",
            "code": "unavailable",
            "service": "yazio",
            "user_id": str(USER),
            "log_level": "warning",
        },
        {"event": "nutrition_sync_error", "error_type": "TimeoutError", "log_level": "debug"},
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
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.02).refresh(USER), timeout=0.5
        )
    assert closing.is_set()
    assert cancelled.is_set()
    assert clients[0].is_closed
    assert logs[1]["error_type"] == "TimeoutError"


async def test_caller_cancellation_propagates() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise asyncio.CancelledError

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        with capture_logs() as logs, pytest.raises(asyncio.CancelledError):
            await HttpNutritionSync("http://sync-service:8080", client=client).refresh(USER)
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
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.02).refresh(USER), timeout=0.1
        )
    assert request_cancelled.is_set()
    assert closing.is_set()
    assert cleanup_cancelled.is_set()
    assert clients[0].is_closed
    assert logs == [
        {
            "event": "nutrition_sync_failed",
            "code": "unavailable",
            "service": "yazio",
            "user_id": str(USER),
            "log_level": "warning",
        },
        {"event": "nutrition_sync_error", "error_type": "TimeoutError", "log_level": "debug"},
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
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.02).refresh(USER)
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
            HttpNutritionSync("http://sync-service:8080", timeout_s=0.5).refresh(USER)
        )
        await started.wait()
        task.cancel()
        with pytest.raises(asyncio.CancelledError):
            await asyncio.wait_for(task, timeout=0.1)
    assert task.done()
    assert clients[0].is_closed
    assert logs == []
