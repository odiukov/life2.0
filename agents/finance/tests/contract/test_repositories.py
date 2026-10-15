"""One behavior contract for every TransactionRepository / CategoryCache backend."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from finance.adapters.db import finance_repositories
from finance.application.ports import CategoryCache, TransactionRepository
from finance.domain.statement import StatementRow
from finance.testing import InMemoryCategoryCache, InMemoryTransactions, in_memory_uow
from shared.adapters.agent_base import base_repositories
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.config import DatabaseSettings
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

T0 = datetime(2026, 10, 1, tzinfo=UTC)


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    seed_user: Callable[[UUID], Awaitable[None]]


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    async def seed_user(user_id: UUID) -> None:
        return None

    yield Backend(in_memory_uow(InMemoryTransactions(), InMemoryCategoryCache()), seed_user)


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    admin = create_async_engine(urls.admin)

    async def seed_user(user_id: UUID) -> None:
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, name, preferences) VALUES (:id, 'u', CAST(:p AS jsonb))"
                ),
                {"id": user_id, "p": json.dumps({})},
            )

    try:
        yield Backend(
            SqlUnitOfWorkFactory(engine, {**base_repositories(), **finance_repositories()}),
            seed_user,
        )
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


def row(n: int, *, direction: str = "OUT", amount: str = "10.00", days: int = 0) -> StatementRow:
    return StatementRow(
        txn_id=f"pyn-pdf-{n:016d}",
        ts=T0 + timedelta(days=days),
        direction=direction,  # type: ignore[arg-type]
        amount=Decimal(amount),
        currency="USD",
        description=f"Shop {n}",
        raw={"date": "x"},
    )


async def test_add_new_is_idempotent_per_user(backend: Backend) -> None:
    me, other = uuid4(), uuid4()
    await backend.seed_user(me)
    await backend.seed_user(other)
    async with backend.uow.for_user(me) as tx:
        assert await tx.repo(TransactionRepository).add_new(me, [row(1), row(2)]) == 2
    async with backend.uow.for_user(me) as tx:
        assert await tx.repo(TransactionRepository).add_new(me, [row(2), row(3)]) == 1
    async with backend.uow.for_user(other) as tx:
        assert await tx.repo(TransactionRepository).add_new(other, [row(1)]) == 1
    async with backend.uow.for_user(me) as tx:
        assert [t.txn_id for t in await tx.repo(TransactionRepository).all(me)] == [
            row(1).txn_id,
            row(2).txn_id,
            row(3).txn_id,
        ]


async def test_categories_and_cache(backend: Backend) -> None:
    me = uuid4()
    await backend.seed_user(me)
    async with backend.uow.for_user(me) as tx:
        repo = tx.repo(TransactionRepository)
        await repo.add_new(me, [row(1), row(2)])
        assert await repo.uncategorized(me, [row(1).txn_id, row(2).txn_id, "missing"]) == {
            row(1).txn_id: "Shop 1",
            row(2).txn_id: "Shop 2",
        }
        await repo.set_categories(me, {row(1).txn_id: "food"})
        assert await repo.uncategorized(me, [row(1).txn_id, row(2).txn_id]) == {
            row(2).txn_id: "Shop 2"
        }
        cache = tx.repo(CategoryCache)
        await cache.put(me, {"shop": "food"})
        await cache.put(me, {"shop": "other", "bar": "food"})
        assert await cache.get(me, ["shop", "bar", "none"]) == {"shop": "other", "bar": "food"}


async def test_between_is_half_open_and_ordered(backend: Backend) -> None:
    me = uuid4()
    await backend.seed_user(me)
    async with backend.uow.for_user(me) as tx:
        await tx.repo(TransactionRepository).add_new(
            me, [row(3, days=2), row(1, days=0), row(2, days=1)]
        )
    async with backend.uow.for_user(me) as tx:
        found = await tx.repo(TransactionRepository).between(me, T0, T0 + timedelta(days=2))
    assert [t.txn_id for t in found] == [row(1).txn_id, row(2).txn_id]
    assert found[0].amount == Decimal("10.00")
    assert found[0].category is None
