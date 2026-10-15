from collections.abc import AsyncIterator
from uuid import uuid4

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.db.profile import SqlBodyProfiles
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.config import DatabaseSettings
from shared.ports.profile import BodyProfileRepository
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.fakes import InMemoryBodyProfiles, InMemoryUnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def uow(request: pytest.FixtureRequest) -> AsyncIterator[tuple[UnitOfWorkFactory, object]]:
    user = uuid4()
    if request.param == "memory":
        yield InMemoryUnitOfWorkFactory({BodyProfileRepository: InMemoryBodyProfiles()}), user
        return
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    admin = create_async_engine(urls.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, preferences) VALUES (:u, 'u', '{\"locale\": \"ru\"}'::jsonb)"
            ),
            {"u": user},
        )
    await admin.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    try:
        yield SqlUnitOfWorkFactory(engine, {BodyProfileRepository: SqlBodyProfiles}), user
    finally:
        await engine.dispose()


async def test_merge_and_remove_keep_other_preferences(uow) -> None:
    factory, user = uow
    async with factory.for_user(user) as tx:
        repo = tx.repo(BodyProfileRepository)
        assert await repo.get(user) == {}
        assert await repo.update(user, {"height_cm": 180, "weight_kg": 81.4}) == {
            "height_cm": 180,
            "weight_kg": 81.4,
        }
        assert await repo.update(user, {"weight_kg": None, "age": 35}) == {
            "height_cm": 180,
            "age": 35,
        }
    async with factory.for_user(user) as tx:
        assert await tx.repo(BodyProfileRepository).get(user) == {"height_cm": 180, "age": 35}


@pytest.mark.integration
async def test_sql_keeps_the_locale(clean_db: PostgresUrls) -> None:
    user = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(
            text(
                "INSERT INTO users (id, name, preferences) VALUES (:u, 'u', '{\"locale\": \"ru\"}'::jsonb)"
            ),
            {"u": user},
        )
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    try:
        factory = SqlUnitOfWorkFactory(engine, {BodyProfileRepository: SqlBodyProfiles})
        async with factory.for_user(user) as tx:
            await tx.repo(BodyProfileRepository).update(user, {"height_cm": 180})
        async with admin.connect() as conn:
            assert (
                await conn.execute(
                    text("SELECT preferences->>'locale' FROM users WHERE id=:u"), {"u": user}
                )
            ).scalar_one() == "ru"
    finally:
        await engine.dispose()
        await admin.dispose()
