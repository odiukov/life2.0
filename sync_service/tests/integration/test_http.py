"""The HTTP surface on PostgreSQL with scripted Garmin/Yazio clients."""

import base64
from collections.abc import AsyncIterator
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import httpx
import pytest
from shared.testing.fakes import FakeScheduler, FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from structlog.testing import capture_logs
from sync.application.ports import AuthFailed
from sync.composition import SyncRuntime, build_runtime
from sync.domain.garmin import GarminBundle
from sync.main import create_app
from sync.settings import SyncServiceSettings
from sync.testing import FakeGarminClient
from sync_fixtures import BODY_ENTRIES, STATS

pytestmark = pytest.mark.integration
KEY = base64.b64encode(bytes(range(32))).decode()


@pytest.fixture
async def world(
    clean_db: PostgresUrls,
) -> AsyncIterator[tuple[httpx.AsyncClient, SyncRuntime, UUID, FakeGarminClient]]:
    user = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:u, 'u', 'Europe/Lisbon')"),
            {"u": user},
        )
    await admin.dispose()
    settings = SyncServiceSettings.model_validate(
        {"database": {"dsn": clean_db.rw}, "secrets": {"key": KEY}}
    )
    garmin = FakeGarminClient(GarminBundle(stats=((date(2026, 10, 13), STATS),)))
    runtime = build_runtime(
        settings,
        garmin=garmin,
        scheduler=FakeScheduler(),
        clock=FixedClock(datetime(2026, 10, 13, 8, 5, tzinfo=UTC)),
    )
    app = create_app(runtime)
    async with (
        app.router.lifespan_context(app),
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://sync") as client,
    ):
        yield client, runtime, user, garmin


async def connect_garmin(runtime: SyncRuntime, user: UUID) -> None:
    from shared.ports.credentials import CredentialStore

    async with runtime.uow.for_user(user) as tx:  # seed through the real, sealing store
        await tx.repo(CredentialStore).put(user, "garmin", {"email": "a@b.c", "password": "pw"})


async def test_sync_user_twice_answers_already_fresh(world) -> None:  # type: ignore[no-untyped-def]
    client, runtime, user, garmin = world
    await connect_garmin(runtime, user)
    first = await client.post("/sync/user", json={"user_id": str(user)})
    assert first.status_code == 200
    assert first.json()["results"] == [
        {"service": "garmin", "status": "ok", "written": 1, "unchanged": 0},
        {"service": "yazio", "status": "disabled", "written": 0, "unchanged": 0},
    ]
    second = await client.post("/sync/user", json={"user_id": str(user), "services": ["garmin"]})
    assert second.json()["results"] == [
        {"service": "garmin", "status": "already_fresh", "written": 0, "unchanged": 0}
    ]
    assert len(garmin.calls) == 1


async def test_bad_requests_are_rejected(world) -> None:  # type: ignore[no-untyped-def]
    client, _, user, _ = world
    assert (await client.post("/sync/user", json={"user_id": "nope"})).status_code == 422
    assert (
        await client.post("/sync/user", json={"user_id": str(user), "services": ["fitbit"]})
    ).status_code == 422
    assert (
        await client.post("/sync/body", json={"data": BODY_ENTRIES})
    ).status_code == 422  # user_id required
    assert (await client.post("/sync")).status_code in (404, 405)
    assert (await client.post("/sync/nutrition")).status_code in (404, 405)


async def test_body_is_written_for_the_given_user(world) -> None:  # type: ignore[no-untyped-def]
    client, _, user, _ = world
    response = await client.post("/sync/body", json={"user_id": str(user), "data": BODY_ENTRIES})
    assert response.json() == {"written": 2, "unchanged": 0}


async def test_credential_check_keeps_the_legacy_contract(world) -> None:  # type: ignore[no-untyped-def]
    client, _, _, garmin = world
    ok = await client.post("/integrations/garmin/test", json={"email": "a@b.c", "password": "pw"})
    assert (ok.status_code, ok.json()) == (200, {"ok": True})
    garmin.check_error = AuthFailed()
    bad = await client.post("/integrations/garmin/test", json={"email": "a@b.c", "password": "pw"})
    assert (bad.status_code, bad.json()) == (
        401,
        {"detail": "invalid Garmin credentials", "code": "auth_failed"},
    )
    off = await client.post("/integrations/yazio/test", json={"email": "a@b.c", "password": "pw"})
    assert (off.status_code, off.json()["code"]) == (502, "disabled")
    assert (
        await client.post("/integrations/fitbit/test", json={"email": "a", "password": "b"})
    ).status_code == 404


async def test_sync_all_is_a_deprecated_wrapper(world) -> None:  # type: ignore[no-untyped-def]
    client, runtime, user, garmin = world
    await connect_garmin(runtime, user)
    with capture_logs() as logs:
        response = await client.post("/sync/all")
    assert response.json() == {"users": 1, "failed": 0}
    assert any(e["event"] == "sync_all_deprecated" for e in logs)
    assert len(garmin.calls) == 1


async def test_lifespan_schedules_the_due_job(world) -> None:  # type: ignore[no-untyped-def]
    _, runtime, _, _ = world
    scheduler = runtime.scheduler
    assert isinstance(scheduler, FakeScheduler)
    assert scheduler.intervals == {"sync_due": 15}
    assert scheduler.running
