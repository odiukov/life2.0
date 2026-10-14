"""One contract for CredentialStore backends."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, field
from uuid import UUID, uuid4

import pytest
from shared.adapters.db.credentials import sql_credential_store
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.secrets import AesGcmSecretBox
from shared.config import DatabaseSettings
from shared.ports.credentials import CredentialStore
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.fakes import InMemoryCredentialStore, InMemoryUnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

KEY = bytes(range(32))


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    user: UUID
    other: UUID = field(default_factory=uuid4)


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    yield Backend(InMemoryUnitOfWorkFactory({CredentialStore: InMemoryCredentialStore()}), uuid4())


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    user, other = uuid4(), uuid4()
    admin = create_async_engine(urls.admin)
    async with admin.begin() as conn:
        for actor in (user, other):
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": actor})
    await admin.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    try:
        yield Backend(
            SqlUnitOfWorkFactory(
                engine, {CredentialStore: sql_credential_store(AesGcmSecretBox(KEY))}
            ),
            user,
            other,
        )
    finally:
        await engine.dispose()


BACKENDS: dict[str, Callable[[pytest.FixtureRequest], AsyncIterator[Backend]]] = {
    "memory": memory_backend,
    "sql": sql_backend,
}


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = BACKENDS[request.param](request)
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


async def test_put_get_merge_delete(backend: Backend) -> None:
    async with backend.uow.for_user(backend.user) as uow:
        store = uow.repo(CredentialStore)
        assert await store.get(backend.user, "garmin") is None
        await store.put(backend.user, "garmin", {"email": "a@b.c", "password": "pw"})
        await store.merge(backend.user, "garmin", {"garmin_token": "tok"})
        assert await store.get(backend.user, "garmin") == {
            "email": "a@b.c",
            "password": "pw",
            "garmin_token": "tok",
        }
        await store.put(backend.user, "garmin", {"email": "x@y.z", "password": "new"})  # replaces
        assert await store.get(backend.user, "garmin") == {"email": "x@y.z", "password": "new"}
        await store.delete(backend.user, "garmin")
        assert await store.get(backend.user, "garmin") is None


async def test_put_rejects_actor_outside_transaction_tenant(backend: Backend) -> None:
    from sqlalchemy.exc import DBAPIError

    for actor in (backend.user, backend.other):
        async with backend.uow.for_user(actor) as uow:
            await uow.repo(CredentialStore).put(actor, "garmin", {"marker": str(actor)})
    with pytest.raises((PermissionError, DBAPIError)):
        async with backend.uow.for_user(backend.user) as uow:
            await uow.repo(CredentialStore).put(backend.other, "garmin", {"marker": "changed"})
    for actor in (backend.user, backend.other):
        async with backend.uow.for_user(actor) as uow:
            assert await uow.repo(CredentialStore).get(actor, "garmin") == {"marker": str(actor)}
