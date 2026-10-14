"""One behavior contract for every kitchen repository backend."""

from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from kitchen.adapters.db import kitchen_uow
from kitchen.application.ports import (
    BatchRepository,
    ClarificationRepository,
    HouseholdContext,
    HouseholdView,
    LoggedChange,
    OperationGroup,
    OperationLog,
    PendingClarification,
    UserLocales,
)
from kitchen.domain.model import Status
from kitchen.testing import KitchenMemory, in_memory_uow, make_batch
from shared.adapters.db.engine import create_engine
from shared.config import DatabaseSettings
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

NOW = datetime.now(UTC).replace(microsecond=0)


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    user: UUID


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    user = uuid4()
    memory = KitchenMemory(HouseholdContext(uuid4(), "Europe/Lisbon", {user: "Аня"}))
    memory.locales.locales[user] = "en"
    yield Backend(in_memory_uow(memory), user)


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    user = uuid4()
    rw = create_async_engine(urls.rw)
    async with rw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        await conn.execute(text("SELECT household_ensure('Аня', 'Europe/Lisbon')"))
        await conn.execute(
            text("""UPDATE users SET preferences = '{"locale": "en"}'::jsonb WHERE id = :u"""),
            {"u": user},
        )
    await rw.dispose()
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    try:
        yield Backend(kitchen_uow(engine), user)
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


async def test_household_view_and_locale(backend: Backend) -> None:
    async with backend.uow.for_user(backend.user) as uow:
        context = await uow.repo(HouseholdView).current()
        assert context is not None
        assert context.timezone == "Europe/Lisbon"
        assert context.members[backend.user] == "Аня"
        assert await uow.repo(UserLocales).locale(backend.user) == "en"


async def test_batches_add_save_restore_delete_and_last_groups(backend: Backend) -> None:
    g1, g2 = uuid4(), uuid4()
    async with backend.uow.for_user(backend.user) as uow:
        repo = uow.repo(BatchRepository)
        await repo.lock()
        milk = await repo.add(make_batch(added_at=NOW, added_by=backend.user), group_id=g1)
        bread = await repo.add(
            make_batch(
                name="хлеб",
                display_name="хлеб",
                added_at=NOW + timedelta(seconds=1),
                expires_on=milk.expires_on,
            ),
            group_id=g1,
        )
        assert [b.pk for b in await repo.list_active()] == [milk.pk, bread.pk]
        await repo.save(replace(milk, quantity=Decimal("500.000")), group_id=g2)
        assert (await repo.get(milk.pk)).quantity == Decimal("500.000")  # type: ignore[union-attr]
        assert await repo.last_groups([milk.pk, bread.pk, uuid4()]) == {milk.pk: g2, bread.pk: g1}
        await repo.save(replace(bread, status=Status.CONSUMED), group_id=g2)
        assert [b.pk for b in await repo.list_active()] == [milk.pk]
        await repo.restore(milk)
        assert (await repo.get(milk.pk)).quantity == milk.quantity  # type: ignore[union-attr]
        assert (await repo.last_groups([milk.pk]))[milk.pk] is None
        await repo.delete(milk.pk)
        assert await repo.get(milk.pk) is None


async def test_operation_log(backend: Backend) -> None:
    group = OperationGroup(
        id=uuid4(),
        user_id=backend.user,
        created_at=NOW,
        source="text",
        changes=(LoggedChange("add", uuid4(), None, {"name": "молоко"}),),
    )
    later = replace(group, id=uuid4(), created_at=NOW + timedelta(seconds=5))
    async with backend.uow.for_user(backend.user) as uow:
        log = uow.repo(OperationLog)
        await log.add(group)
        await log.add(later)
        assert (await log.get(group.id)) == group
        assert (await log.latest_for_user(backend.user)).id == later.id  # type: ignore[union-attr]
        await log.mark_undone(later.id, at=NOW, by=backend.user)
        assert (await log.get(later.id)).undone_at == NOW  # type: ignore[union-attr]
        assert (await log.latest_for_user(backend.user)).id == group.id  # type: ignore[union-attr]
        assert await log.get(uuid4()) is None


async def test_clarifications_replace_and_expire(backend: Backend) -> None:
    first = PendingClarification(
        "доели сыр", "сыр", "ambiguous", ("a", "b"), NOW + timedelta(minutes=30)
    )
    second = replace(first, ref="кефир")
    async with backend.uow.for_user(backend.user) as uow:
        repo = uow.repo(ClarificationRepository)
        await repo.put(backend.user, first)
        await repo.put(backend.user, second)
        assert await repo.get(backend.user, now=NOW) == second
        assert await repo.get(backend.user, now=second.expires_at) is None
        assert await repo.get(backend.user, now=NOW + timedelta(hours=1)) is None
        await repo.delete(backend.user)
        assert await repo.get(backend.user, now=NOW) is None


async def test_latest_group_ties_follow_insertion_order(backend: Backend) -> None:
    first = OperationGroup(UUID(int=2), backend.user, NOW, "text", ())
    second = replace(first, id=UUID(int=1))
    async with backend.uow.for_user(backend.user) as uow:
        log = uow.repo(OperationLog)
        await log.add(first)
        await log.add(second)
        assert await log.latest_for_user(backend.user) == second
        await log.mark_undone(second.id, at=NOW, by=backend.user)
        assert await log.latest_for_user(backend.user) == first


async def test_repositories_roll_back_together(backend: Backend) -> None:
    group = OperationGroup(uuid4(), backend.user, NOW, "text", ())
    pending = PendingClarification(
        "milk", "milk", "ambiguous", ("a", "b"), NOW + timedelta(minutes=30)
    )

    async def abort() -> None:
        async with backend.uow.for_user(backend.user) as uow:
            repo = uow.repo(BatchRepository)
            await repo.lock()
            batch = await repo.add(make_batch(added_by=backend.user), group_id=group.id)
            await uow.repo(OperationLog).add(group)
            await uow.repo(ClarificationRepository).put(backend.user, pending)
            batch_ids.append(batch.pk)
            raise ValueError("abort")

    batch_ids: list[UUID] = []
    with pytest.raises(ValueError, match="abort"):
        await abort()
    async with backend.uow.for_user(backend.user) as uow:
        assert await uow.repo(BatchRepository).get(batch_ids[0]) is None
        assert await uow.repo(OperationLog).get(group.id) is None
        assert await uow.repo(ClarificationRepository).get(backend.user, now=NOW) is None
