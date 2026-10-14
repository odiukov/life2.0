from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.notifications import notification_repositories
from shared.config import DatabaseSettings
from shared.ports.notifications import Notification, NotificationInbox, PushTokens
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.fakes import (
    InMemoryNotificationInbox,
    InMemoryPushTokens,
    InMemoryUnitOfWorkFactory,
)
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

T0 = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
N = Notification("kitchen.digest", "Скоро испортятся", "курица", {"route": "/kitchen"})


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    seed_user: Callable[[UUID], object]


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    async def seed(user: UUID) -> None:
        return None

    yield Backend(
        InMemoryUnitOfWorkFactory(
            {NotificationInbox: InMemoryNotificationInbox(), PushTokens: InMemoryPushTokens()}
        ),
        seed,
    )


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    admin = create_async_engine(urls.admin)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))

    async def seed(user: UUID) -> None:
        async with admin.begin() as conn:
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": user})

    try:
        yield Backend(SqlUnitOfWorkFactory(engine, notification_repositories()), seed)
    finally:
        await engine.dispose()
        await admin.dispose()


BACKENDS = {"memory": memory_backend, "sql": sql_backend}


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = BACKENDS[request.param](request)
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


async def test_inbox_contract(backend: Backend) -> None:
    user = uuid4()
    await backend.seed_user(user)  # type: ignore[misc]
    async with backend.uow.for_user(user) as uow:
        inbox = uow.repo(NotificationInbox)
        first = await inbox.add(user, N, created_at=T0)
        second = await inbox.add(user, N, created_at=T0 + timedelta(minutes=1))
        assert [i.id for i in await inbox.page(user, before=None, limit=10)] == [second, first]
        assert [
            i.id for i in await inbox.page(user, before=T0 + timedelta(minutes=1), limit=10)
        ] == [first]
        item = (await inbox.page(user, before=None, limit=1))[0]
        assert (item.title, item.data) == ("Скоро испортятся", {"route": "/kitchen"})
        assert await inbox.unread_count(user) == 2
        assert await inbox.mark_read(user, first, at=T0) is True
        assert await inbox.mark_read(user, uuid4(), at=T0) is False
        assert await inbox.mark_all_read(user, at=T0) == 1
        assert await inbox.unread_count(user) == 0


async def test_push_tokens_contract(backend: Backend) -> None:
    user = uuid4()
    await backend.seed_user(user)  # type: ignore[misc]
    async with backend.uow.for_user(user) as uow:
        tokens = uow.repo(PushTokens)
        await tokens.upsert(user, "ExponentPushToken[1]", "ios", at=T0)
        await tokens.upsert(user, "ExponentPushToken[1]", "ios", at=T0 + timedelta(days=1))
        assert await tokens.for_user(user) == ["ExponentPushToken[1]"]
        await tokens.delete(user, "ExponentPushToken[1]")
        assert await tokens.for_user(user) == []
