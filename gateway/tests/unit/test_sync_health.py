import logging
from datetime import UTC, datetime
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from fastapi import FastAPI, HTTPException
from gateway.sync import build_health_router

USER = uuid4()
SYNC = "http://sync.test"
SAMPLE = {
    "type": "stepCount",
    "start": datetime(2026, 10, 13, 9, tzinfo=UTC).isoformat(),
    "value": 4321,
    "unit": "count",
    "source": "iPhone",
}


async def me(authorization: str | None = None) -> UUID:
    return USER


async def nobody() -> UUID:
    raise HTTPException(status_code=401, detail="missing_bearer_token")


def api(auth=me) -> FastAPI:  # type: ignore[no-untyped-def]
    app = FastAPI()
    app.include_router(build_health_router(httpx.AsyncClient(), SYNC, auth))
    return app


async def post(app: FastAPI, body: object) -> httpx.Response:
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://t"
    ) as client:
        return await client.post("/sync/health", json=body)


@respx.mock
async def test_forwards_the_batch_for_the_caller_only() -> None:
    route = respx.post(f"{SYNC}/sync/healthkit").respond(
        json={"inserted": 1, "received": 1, "aggregated": {"daily_stats": 1}}
    )
    response = await post(api(), {"samples": [SAMPLE]})
    assert response.json() == {"inserted": 1, "received": 1, "aggregated": {"daily_stats": 1}}
    sent = route.calls.last.request
    assert b'"user_id":"' + str(USER).encode() + b'"' in sent.content


async def test_requires_auth() -> None:
    assert (await post(api(nobody), {"samples": [SAMPLE]})).status_code == 401


async def test_rejects_huge_batches_before_calling_sync() -> None:
    assert (await post(api(), {"samples": [SAMPLE] * 501})).status_code == 422


@respx.mock
async def test_sync_service_down_is_502() -> None:
    respx.post(f"{SYNC}/sync/healthkit").mock(side_effect=httpx.ConnectError("down"))
    response = await post(api(), {"samples": [SAMPLE]})
    assert response.status_code == 502
    assert response.json() == {"detail": "sync_unavailable"}


async def test_validation_errors_do_not_echo_or_log_values(
    caplog: pytest.LogCaptureFixture,
) -> None:
    caplog.set_level(logging.DEBUG)
    response = await post(api(), {"samples": [{**SAMPLE, "start": "not-a-date", "value": 98765}]})
    assert response.status_code == 422
    assert "98765" not in caplog.text


@respx.mock
async def test_sync_server_error_is_private_502() -> None:
    respx.post(f"{SYNC}/sync/healthkit").respond(503, json={"detail": "private server message"})
    response = await post(api(), {"samples": [SAMPLE]})
    assert response.status_code == 502
    assert response.json() == {"detail": "sync_unavailable"}


async def test_invalid_health_values_are_not_echoed() -> None:
    response = await post(api(), {"samples": [{**SAMPLE, "start": "private-invalid-date"}]})
    assert response.status_code == 422
    assert "private-invalid-date" not in response.text
