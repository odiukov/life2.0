import asyncio
from uuid import UUID, uuid4

import httpx
import respx
from fastapi import FastAPI
from gateway.sync import SyncTrigger, build_trigger_router

USER = uuid4()


async def me() -> UUID:
    return USER


@respx.mock
async def test_trigger_answers_at_once_and_syncs_only_the_caller() -> None:
    gate = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        await gate.wait()
        return httpx.Response(200, json={"user_id": str(USER), "results": []})

    route = respx.post("http://sync.test/sync/user").mock(side_effect=slow)
    async with httpx.AsyncClient() as http:
        trigger = SyncTrigger(http, "http://sync.test", concurrency=1)
        api = FastAPI()
        api.include_router(build_trigger_router(trigger, me))
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=api), base_url="http://t"
        ) as client:
            first = await client.post("/sync/trigger")
            second = await client.post("/sync/trigger")
        assert first.status_code == 202
        assert first.json() == {"ok": True}
        assert second.status_code == 202
        gate.set()
        await trigger.drain()
        await trigger.aclose()
    assert route.call_count == 2
    assert all(call.request.read() == f'{{"user_id":"{USER}"}}'.encode() for call in route.calls)


async def test_concurrency_limit_and_shutdown_cancel_waiting_work():
    entered, release = asyncio.Event(), asyncio.Event()
    requests = []
    cancelled = asyncio.Event()

    async def slow(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        entered.set()
        try:
            await release.wait()
        finally:
            cancelled.set()
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(slow)) as http:
        trigger = SyncTrigger(http, "http://sync.test", concurrency=1)
        trigger.start(USER)
        await asyncio.wait_for(entered.wait(), timeout=1)
        trigger.start(USER)
        await asyncio.sleep(0)
        assert len(requests) == 1
        await asyncio.wait_for(trigger.aclose(), timeout=1)
        assert cancelled.is_set()
        assert len(requests) == 1


async def test_failed_sync_logs_type_only_and_next_sync_runs(caplog):
    requests = []

    async def fail_once(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        if len(requests) == 1:
            raise httpx.ConnectError("private connection information")
        return httpx.Response(200)

    async with httpx.AsyncClient(transport=httpx.MockTransport(fail_once)) as http:
        trigger = SyncTrigger(http, "http://sync.test", concurrency=1)
        trigger.start(USER)
        trigger.start(USER)
        await trigger.drain()
        await trigger.aclose()
    assert len(requests) == 2
    assert "private connection information" not in caplog.text
