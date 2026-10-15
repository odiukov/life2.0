"""One contract for HouseholdCredentialStore backends: A and B share a household, C has its own."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest
from household.adapters.db import household_uow
from household.application.service import HouseholdService
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.db.household_credentials import sql_household_credentials
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.secrets import AesGcmSecretBox
from shared.config import DatabaseSettings
from shared.ports.credentials import CredentialsUnreadable
from shared.ports.household_credentials import HouseholdCredentialStore, NoHousehold
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.fakes import InMemoryHouseholdCredentials, InMemoryUnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

KEY = bytes(range(32))
PAYLOAD = {"base_url": "http://ha.local:8123", "token": "token-1"}


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    a: UUID
    b: UUID
    c: UUID
    loner: UUID  # belongs to no household
    reader: Callable[[bytes], UnitOfWorkFactory] | None = None  # SQL only: same DB, another key


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    store = InMemoryHouseholdCredentials()
    a, b, c, loner = uuid4(), uuid4(), uuid4(), uuid4()
    shared_home = uuid4()
    store.seed_member(a, shared_home, "Ana")
    store.seed_member(b, shared_home, "Bo")
    store.seed_member(c, uuid4(), "Cy")
    yield Backend(InMemoryUnitOfWorkFactory({HouseholdCredentialStore: store}), a, b, c, loner)


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    households = HouseholdService(household_uow(engine), SystemClock())
    a, b, c, loner = uuid4(), uuid4(), uuid4(), uuid4()
    admin = create_async_engine(urls.admin)
    async with admin.begin() as conn:
        for user in (a, b, c, loner):
            await conn.execute(
                text("INSERT INTO users (id, name) VALUES (:u, 'Member')"), {"u": user}
            )
    await admin.dispose()
    for user in (a, b, c):
        await households.ensure(user)
    invite = await households.create_invite(a)
    await households.join(b, invite.code.value)

    def factory(key: bytes) -> UnitOfWorkFactory:
        return SqlUnitOfWorkFactory(
            engine, {HouseholdCredentialStore: sql_household_credentials(AesGcmSecretBox(key))}
        )

    try:
        yield Backend(factory(KEY), a, b, c, loner, factory)
    finally:
        await engine.dispose()


BACKENDS = {"memory": memory_backend, "sql": sql_backend}


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = BACKENDS[request.param](request)
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


async def test_members_share_one_connection_and_versions_grow(backend: Backend) -> None:
    async with backend.uow.for_user(backend.a) as tx:
        first = await tx.repo(HouseholdCredentialStore).put("ha", PAYLOAD, actor=backend.a)
    async with backend.uow.for_user(backend.b) as tx:
        seen = await tx.repo(HouseholdCredentialStore).get("ha")
        second = await tx.repo(HouseholdCredentialStore).put(
            "ha", {**PAYLOAD, "token": "token-2"}, actor=backend.b
        )
    assert first.version >= 1
    assert second.version > first.version
    assert seen is not None
    assert seen.payload == PAYLOAD
    assert seen.updated_by == backend.a
    assert seen.updated_by_name  # the member's display name in that household
    assert seen.household_id == second.household_id


async def test_other_households_see_nothing(backend: Backend) -> None:
    async with backend.uow.for_user(backend.a) as tx:
        await tx.repo(HouseholdCredentialStore).put("ha", PAYLOAD, actor=backend.a)
    async with backend.uow.for_user(backend.c) as tx:
        store = tx.repo(HouseholdCredentialStore)
        assert await store.get("ha") is None
        assert await store.delete("ha") is False
    async with backend.uow.for_user(backend.a) as tx:
        still = await tx.repo(HouseholdCredentialStore).get("ha")
    assert still is not None
    assert still.payload == PAYLOAD


async def test_no_household_cannot_store(backend: Backend) -> None:
    async with backend.uow.for_user(backend.loner) as tx:
        store = tx.repo(HouseholdCredentialStore)
        assert await store.household_id() is None
        assert await store.get("ha") is None
        with pytest.raises(NoHousehold):
            await store.put("ha", PAYLOAD, actor=backend.loner)
    async with backend.uow.for_user(backend.a) as tx:
        mine = await tx.repo(HouseholdCredentialStore).household_id()
    async with backend.uow.for_user(backend.b) as tx:
        theirs = await tx.repo(HouseholdCredentialStore).household_id()
    assert mine is not None
    assert mine == theirs


async def test_delete_removes_it_for_everyone(backend: Backend) -> None:
    async with backend.uow.for_user(backend.a) as tx:
        await tx.repo(HouseholdCredentialStore).put("ha", PAYLOAD, actor=backend.a)
    async with backend.uow.for_user(backend.b) as tx:
        assert await tx.repo(HouseholdCredentialStore).delete("ha") is True
    async with backend.uow.for_user(backend.a) as tx:
        assert await tx.repo(HouseholdCredentialStore).get("ha") is None


@pytest.mark.integration
async def test_wrong_key_is_unreadable(request: pytest.FixtureRequest) -> None:
    generator = sql_backend(request)
    backend = await generator.__anext__()
    try:
        async with backend.uow.for_user(backend.a) as tx:
            await tx.repo(HouseholdCredentialStore).put("ha", PAYLOAD, actor=backend.a)
        assert backend.reader is not None
        async with backend.reader(bytes(range(1, 33))).for_user(backend.a) as tx:
            with pytest.raises(CredentialsUnreadable):
                await tx.repo(HouseholdCredentialStore).get("ha")
    finally:
        await generator.aclose()


async def test_reconnect_never_reuses_a_generation(backend: Backend) -> None:
    async with backend.uow.for_user(backend.a) as tx:
        store = tx.repo(HouseholdCredentialStore)
        before = await store.put("ha", PAYLOAD, actor=backend.a)
        await store.delete("ha")
        after = await store.put("ha", PAYLOAD, actor=backend.a)
    assert after.version > before.version
