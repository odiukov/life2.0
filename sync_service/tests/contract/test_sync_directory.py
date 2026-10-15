"""One contract for SyncDirectory: the SQL definer function and its in-memory twin agree."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.secrets import AesGcmSecretBox
from shared.config import DatabaseSettings
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sync.adapters.db import sync_uow
from sync.application.ports import SyncDirectory, SyncStatus
from sync.testing import MemoryBackend

NOW = datetime(2026, 10, 13, 9, 30, tzinfo=UTC)  # 10:30 Lisbon, 05:30 New York


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    seed_user: Callable[[str], Awaitable[UUID]]
    seed_credentials: Callable[[UUID, str], Awaitable[None]]
    seed_state: Callable[[UUID, str, SyncStatus], Awaitable[None]]


async def memory() -> AsyncIterator[Backend]:
    backend = MemoryBackend()

    async def user(tz: str) -> UUID:
        uid = uuid4()
        backend.users.seed(uid, timezone=tz)
        return uid

    async def creds(uid: UUID, service: str) -> None:
        backend.credentials.rows[(uid, service)] = {"email": "x", "password": "y"}

    async def state(uid: UUID, service: str, status: SyncStatus) -> None:
        backend.state.rows[(uid, service)] = status

    yield Backend(backend.uow, user, creds, state)


async def sql(urls: PostgresUrls) -> AsyncIterator[Backend]:
    admin = create_async_engine(urls.admin)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    box = AesGcmSecretBox(bytes(range(32)))

    async def run(statement: str, **params: object) -> None:
        async with admin.begin() as conn:
            await conn.execute(text(statement), params)

    async def user(tz: str) -> UUID:
        uid = uuid4()
        await run("INSERT INTO users (id, name, timezone) VALUES (:u, 'u', :tz)", u=uid, tz=tz)
        return uid

    async def creds(uid: UUID, service: str) -> None:
        await run(
            "INSERT INTO integrations_credentials (user_id, service, payload_enc) VALUES (:u, :s, :p)",
            u=uid,
            s=service,
            p=box.seal(b'{"email":"x","password":"y"}'),
        )

    async def state(uid: UUID, service: str, status: SyncStatus) -> None:
        await run(
            "INSERT INTO integration_sync_state VALUES (:u, :s, :a, :ok, :e)",
            u=uid,
            s=service,
            a=status.last_attempt_at,
            ok=status.last_success_at,
            e=status.last_error,
        )

    try:
        yield Backend(sync_uow(engine, box), user, creds, state)
    finally:
        await admin.dispose()
        await engine.dispose()


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = memory() if request.param == "memory" else sql(request.getfixturevalue("clean_db"))
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


async def due(backend: Backend, at: datetime, hour: int = 9) -> dict[UUID, tuple[str, ...]]:
    async with backend.uow.system() as tx:
        return {d.user_id: d.services for d in await tx.repo(SyncDirectory).due(at, hour)}


async def test_due_rule(backend: Backend) -> None:
    lisbon, new_york = (
        await backend.seed_user("Europe/Lisbon"),
        await backend.seed_user("America/New_York"),
    )
    synced = await backend.seed_user("Europe/Lisbon")
    failing = await backend.seed_user("Europe/Lisbon")
    locked = await backend.seed_user("Europe/Lisbon")
    for uid in (lisbon, new_york, synced, failing, locked):
        await backend.seed_credentials(uid, "garmin")
    await backend.seed_credentials(lisbon, "yazio")
    await backend.seed_state(
        synced, "garmin", SyncStatus(NOW - timedelta(hours=1), NOW - timedelta(hours=1), None)
    )
    await backend.seed_state(
        failing, "garmin", SyncStatus(NOW - timedelta(minutes=20), None, "unavailable")
    )
    await backend.seed_state(
        locked, "garmin", SyncStatus(NOW - timedelta(hours=2), None, "auth_failed")
    )

    assert await due(backend, NOW) == {lisbon: ("garmin", "yazio")}
    assert await due(backend, NOW + timedelta(hours=1)) == {
        lisbon: ("garmin", "yazio"),
        failing: ("garmin",),
    }
    assert new_york in await due(backend, NOW, hour=0)  # force: no hour gate
    tomorrow = await due(backend, NOW + timedelta(days=1))
    assert {lisbon, synced, failing, locked} <= set(tomorrow)


async def test_invalid_zone_and_exact_retry_boundary(backend: Backend) -> None:
    user = await backend.seed_user("invalid/zone")
    await backend.seed_credentials(user, "garmin")
    await backend.seed_credentials(user, "google_calendar")
    await backend.seed_state(
        user, "garmin", SyncStatus(NOW - timedelta(hours=1), None, "unavailable")
    )
    assert await due(backend, NOW) == {user: ("garmin",)}
    assert await due(backend, NOW, hour=10) == {}


async def test_success_and_auth_failure_use_local_calendar_day(backend: Backend) -> None:
    user = await backend.seed_user("America/New_York")
    await backend.seed_credentials(user, "garmin")
    await backend.seed_credentials(user, "yazio")
    yesterday = datetime(2026, 10, 13, 3, 59, tzinfo=UTC)
    await backend.seed_state(user, "garmin", SyncStatus(yesterday, yesterday, None))
    await backend.seed_state(user, "yazio", SyncStatus(yesterday, None, "auth_failed"))
    assert await due(backend, NOW, hour=0) == {user: ("garmin", "yazio")}


async def test_auth_failed_without_attempt_is_not_due(backend: Backend) -> None:
    user = await backend.seed_user("UTC")
    await backend.seed_credentials(user, "garmin")
    await backend.seed_state(user, "garmin", SyncStatus(None, None, "auth_failed"))
    assert await due(backend, NOW) == {}
