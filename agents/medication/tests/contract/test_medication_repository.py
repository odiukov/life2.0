from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from uuid import UUID, uuid4

import pytest
from medication.adapters.db import medication_repositories
from medication.application.ports import DuplicateMedication, MedicationRepository
from medication.domain.medication import Medication
from medication.testing import InMemoryMedications
from shared.adapters.agent_base import base_repositories
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.config import DatabaseSettings
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.fakes import InMemoryUnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

B12 = Medication(
    id=None,
    name="b12",
    dose="1000 mcg",
    schedule="mon,wed,fri morning",
    notes="with food",
    created_at=None,
)


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    user: UUID


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    user = uuid4()
    yield Backend(InMemoryUnitOfWorkFactory({MedicationRepository: InMemoryMedications()}), user)


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    user = uuid4()
    admin = create_async_engine(urls.admin)
    async with admin.begin() as conn:
        await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": user})
    await admin.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    try:
        yield Backend(
            SqlUnitOfWorkFactory(engine, {**base_repositories(), **medication_repositories()}), user
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


async def test_add_list_duplicate_archive(backend: Backend) -> None:
    async with backend.uow.for_user(backend.user) as uow:
        repo = uow.repo(MedicationRepository)
        mid = await repo.add(B12)
        [stored] = await repo.active()
        assert stored == replace(B12, id=mid, created_at=stored.created_at)
        with pytest.raises(DuplicateMedication):
            await repo.add(B12)
        assert await repo.archive(mid) is True
        assert await repo.archive(mid) is False
        assert await repo.active() == []
        await repo.add(B12)


@pytest.mark.integration
async def test_sql_tenant_isolation(clean_db: PostgresUrls) -> None:
    first, second = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        for uid in (first, second):
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": uid})
    await admin.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    uow = SqlUnitOfWorkFactory(engine, medication_repositories())
    try:
        async with uow.for_user(first) as tx:
            first_id = await tx.repo(MedicationRepository).add(B12)
        async with uow.for_user(second) as tx:
            repo = tx.repo(MedicationRepository)
            assert await repo.active() == []
            assert await repo.archive(first_id) is False
            second_id = await repo.add(B12)
            assert [h.id for h in await repo.active()] == [second_id]
        async with uow.for_user(first) as tx:
            assert [h.id for h in await tx.repo(MedicationRepository).active()] == [first_id]
    finally:
        await engine.dispose()
