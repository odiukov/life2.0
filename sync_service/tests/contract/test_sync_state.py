"""One contract for SyncStateRepository backends."""

import asyncio
from collections.abc import AsyncIterator
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.secrets import AesGcmSecretBox
from shared.config import DatabaseSettings
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import create_async_engine
from sync.adapters.db import sync_uow
from sync.application.ports import SyncStateRepository, SyncStatus
from sync.testing import MemoryBackend

T0 = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[tuple[UnitOfWorkFactory, UUID]]:
    user = uuid4()
    if request.param == "memory":
        yield MemoryBackend().uow, user
        return
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    admin = create_async_engine(urls.admin)
    async with admin.begin() as conn:
        await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": user})
    await admin.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    try:
        yield sync_uow(engine, AesGcmSecretBox(bytes(range(32)))), user
    finally:
        await engine.dispose()


async def test_claim_honours_the_cooldown_and_finish_records_outcomes(
    backend: tuple[UnitOfWorkFactory, UUID],
) -> None:
    uow, user = backend
    cooldown = timedelta(minutes=10)

    async def claim(at: datetime) -> bool:
        async with uow.for_user(user) as tx:
            return await tx.repo(SyncStateRepository).claim(
                user, "garmin", now=at, cooldown=cooldown
            )

    async def status() -> SyncStatus | None:
        async with uow.for_user(user) as tx:
            return await tx.repo(SyncStateRepository).get(user, "garmin")

    assert await status() is None
    assert await claim(T0) is True
    assert await claim(T0 + timedelta(minutes=9)) is False
    assert await claim(T0 + timedelta(minutes=10)) is True
    async with uow.for_user(user) as tx:
        await tx.repo(SyncStateRepository).finish(
            user, "garmin", now=T0 + timedelta(minutes=11), error=None, success=True
        )
    assert await status() == SyncStatus(
        T0 + timedelta(minutes=11), T0 + timedelta(minutes=11), None
    )
    async with uow.for_user(user) as tx:
        await tx.repo(SyncStateRepository).finish(
            user, "garmin", now=T0 + timedelta(hours=1), error="unavailable", success=False
        )
    # a failure keeps the last success
    assert await status() == SyncStatus(
        T0 + timedelta(hours=1), T0 + timedelta(minutes=11), "unavailable"
    )
    async with uow.for_user(user) as tx:  # services are independent
        assert await tx.repo(SyncStateRepository).claim(
            user, "yazio", now=T0 + timedelta(hours=1), cooldown=cooldown
        )


async def test_concurrent_claims_have_one_winner(backend: tuple[UnitOfWorkFactory, UUID]) -> None:
    uow, user = backend

    async def claim() -> bool:
        async with uow.for_user(user) as tx:
            return await tx.repo(SyncStateRepository).claim(
                user, "garmin", now=T0, cooldown=timedelta(minutes=10)
            )

    assert sorted(await asyncio.gather(claim(), claim())) == [False, True]


@pytest.fixture
async def sql_backend(clean_db: PostgresUrls) -> AsyncIterator[tuple[UnitOfWorkFactory, UUID]]:
    user = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": user})
    await admin.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    try:
        yield sync_uow(engine, AesGcmSecretBox(bytes(range(32)))), user
    finally:
        await engine.dispose()


@pytest.mark.integration
async def test_sql_state_enforces_tenant_on_reads_and_writes(
    sql_backend: tuple[UnitOfWorkFactory, UUID],
) -> None:
    uow, user = sql_backend
    async with uow.for_user(user) as tx:
        await tx.repo(SyncStateRepository).finish(user, "garmin", now=T0, error=None, success=True)
    async with uow.for_user(uuid4()) as tx:
        assert await tx.repo(SyncStateRepository).get(user, "garmin") is None
    with pytest.raises(DBAPIError):
        async with uow.for_user(uuid4()) as tx:
            await tx.repo(SyncStateRepository).claim(user, "garmin", now=T0, cooldown=timedelta())
    with pytest.raises(DBAPIError):
        async with uow.for_user(uuid4()) as tx:
            await tx.repo(SyncStateRepository).finish(
                user, "garmin", now=T0, error="unavailable", success=False
            )
    async with uow.for_user(user) as tx:
        assert await tx.repo(SyncStateRepository).get(user, "garmin") == SyncStatus(T0, T0, None)


@pytest.mark.integration
async def test_sql_data_rollback_keeps_separately_committed_token(
    sql_backend: tuple[UnitOfWorkFactory, UUID],
) -> None:
    from shared.ports.credentials import CredentialStore
    from shared.ports.health_logs import HealthLogRepository, HealthLogRow

    uow, user = sql_backend
    async with uow.for_user(user) as tx:
        await tx.repo(CredentialStore).put(user, "garmin", {"garmin_token": "old"})
        await tx.repo(SyncStateRepository).claim(
            user, "garmin", now=T0, cooldown=timedelta(minutes=10)
        )
    async with uow.for_user(user) as tx:
        await tx.repo(CredentialStore).merge(user, "garmin", {"garmin_token": "new"})

    async def failing_write() -> None:
        async with uow.for_user(user) as tx:
            await tx.repo(HealthLogRepository).upsert(
                user,
                HealthLogRow(
                    type="activity",
                    recorded_at=T0,
                    data={"steps": 2},
                    source="garmin",
                    agent="workout",
                ),
            )
            await tx.repo(SyncStateRepository).finish(
                user, "garmin", now=T0, error=None, success=True
            )
            raise RuntimeError("abort")

    with pytest.raises(RuntimeError, match="abort"):
        await failing_write()
    async with uow.for_user(user) as tx:
        assert await tx.repo(CredentialStore).get(user, "garmin") == {"garmin_token": "new"}
        assert await tx.repo(HealthLogRepository).recent(user, types=["activity"]) == []
        assert await tx.repo(SyncStateRepository).get(user, "garmin") == SyncStatus(T0, None, None)
