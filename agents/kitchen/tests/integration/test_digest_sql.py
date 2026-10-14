import hashlib
from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from kitchen.adapters.db import digest_repositories, kitchen_uow
from kitchen.application.digest_job import SendDueDigests
from kitchen.application.ports import DueDigests
from kitchen.application.schema import AddItem, OperationList
from kitchen.application.service import InventoryService
from kitchen.domain.model import Category, Location, Source
from kitchen.domain.units import InputUnit
from kitchen.testing import FakeDueDigests
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.i18n import JsonTranslator
from shared.adapters.notifications import InboxNotificationSender, notification_repositories
from shared.config import DatabaseSettings, find_locales_dir
from shared.ports.notifications import NotificationInbox
from shared.testing.fakes import FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration


async def tenant(raw: AsyncEngine, user: UUID, sql: str, **params: object) -> list[object]:
    async with raw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        result = await conn.execute(text(sql), params)
        return list(result.all()) if result.returns_rows else []


async def household(raw: AsyncEngine, user: UUID, tz: str) -> None:
    await tenant(raw, user, "SELECT household_ensure('u', :tz)", tz=tz)


async def test_due_uses_household_local_date(clean_db: PostgresUrls) -> None:
    raw = create_async_engine(clean_db.rw)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    uow = kitchen_uow(engine, extra=digest_repositories())
    try:
        auckland, lisbon = uuid4(), uuid4()
        await household(raw, auckland, "Pacific/Auckland")
        await household(raw, lisbon, "Europe/Lisbon")

        async def due_at(now: datetime) -> dict[UUID, date]:
            async with uow.system() as tx:
                return {d.owner_id: d.local_date for d in await tx.repo(DueDigests).due(now)}

        assert await due_at(datetime(2026, 10, 14, 4, tzinfo=UTC)) == {}
        assert await due_at(datetime(2026, 10, 14, 5, 30, tzinfo=UTC)) == {
            auckland: date(2026, 10, 14)
        }
        assert await due_at(datetime(2026, 10, 14, 23, 30, tzinfo=UTC)) == {}
        assert lisbon in await due_at(datetime(2026, 10, 25, 18, 5, tzinfo=UTC))
        assert (await due_at(datetime(2026, 10, 24, 17, 5, tzinfo=UTC)))[lisbon] == date(
            2026, 10, 24
        )
    finally:
        await engine.dispose()
        await raw.dispose()


async def test_both_members_get_exactly_one_digest(clean_db: PostgresUrls) -> None:
    raw = create_async_engine(clean_db.rw)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    uow = kitchen_uow(engine, extra=digest_repositories())
    inbox_uow = SqlUnitOfWorkFactory(engine, notification_repositories())
    clock = FixedClock(datetime(2026, 10, 13, 18, 30, tzinfo=UTC))
    try:
        a, b = uuid4(), uuid4()
        await household(raw, a, "Europe/London")
        await household(raw, b, "Europe/London")
        digest = hashlib.sha256(b"DIGEST1").digest()
        await tenant(
            raw,
            a,
            "INSERT INTO household_invites (code_hash, created_by, expires_at) VALUES (:h, :u, now() + interval '1 day')",
            h=digest,
            u=a,
        )
        await tenant(raw, b, "SELECT * FROM household_join(:h)", h=digest)
        await InventoryService(uow, clock).apply(
            a,
            ops=OperationList(
                adds=[
                    AddItem(
                        name="курица",
                        display_name="курица",
                        quantity=1,
                        unit=InputUnit.KG,
                        location=Location.FRIDGE,
                        category=Category.MEAT,
                        expires_on=date(2026, 10, 14),
                    )
                ]
            ),
            refs={},
            source=Source.TEXT,
        )
        job = SendDueDigests(
            uow,
            InboxNotificationSender(inbox_uow, clock),
            JsonTranslator.from_dir(find_locales_dir()),
            clock,
            default_locale="ru",
        )
        assert await job() == 1
        assert await job() == 0
        for user in (a, b):
            async with inbox_uow.for_user(user) as tx:
                items = await tx.repo(NotificationInbox).page(user, before=None, limit=10)
            assert [i.body for i in items] == ["курица (завтра)"]
    finally:
        await engine.dispose()
        await raw.dispose()


async def test_membership_change_after_discovery_never_sends_to_former_member(
    clean_db: PostgresUrls,
) -> None:
    raw = create_async_engine(clean_db.rw)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    repos = digest_repositories()
    uow = kitchen_uow(engine, extra=repos)
    inbox_uow = SqlUnitOfWorkFactory(engine, notification_repositories())
    clock = FixedClock(datetime(2026, 10, 13, 18, 30, tzinfo=UTC))
    try:
        a, b = uuid4(), uuid4()
        await household(raw, a, "Europe/London")
        await household(raw, b, "Europe/London")
        digest = hashlib.sha256(b"DIGEST_MOVE").digest()
        await tenant(
            raw,
            a,
            "INSERT INTO household_invites (code_hash, created_by, expires_at) VALUES (:h, :u, now() + interval '1 day')",
            h=digest,
            u=a,
        )
        await tenant(raw, b, "SELECT * FROM household_join(:h)", h=digest)
        await InventoryService(uow, clock).apply(
            a,
            ops=OperationList(
                adds=[
                    AddItem(
                        name="курица",
                        display_name="курица",
                        quantity=1,
                        unit=InputUnit.KG,
                        location=Location.FRIDGE,
                        category=Category.MEAT,
                        expires_on=date(2026, 10, 13),
                    )
                ]
            ),
            refs={},
            source=Source.TEXT,
        )
        async with uow.system() as tx:
            due = await tx.repo(DueDigests).due(clock.now())
        assert len(due) == 1
        assert set(due[0].member_ids) == {a, b}
        await tenant(raw, b, "SELECT * FROM household_leave()")
        stale_repos = {**repos, DueDigests: lambda conn: FakeDueDigests(due)}
        job = SendDueDigests(
            kitchen_uow(engine, extra=stale_repos),
            InboxNotificationSender(inbox_uow, clock),
            JsonTranslator.from_dir(find_locales_dir()),
            clock,
            default_locale="ru",
        )
        assert await job() == 0
        for user in (a, b):
            async with inbox_uow.for_user(user) as tx:
                assert await tx.repo(NotificationInbox).page(user, before=None, limit=10) == []
        assert await tenant(raw, a, "SELECT COUNT(*) FROM kitchen_digest_runs") == [(0,)]
    finally:
        await engine.dispose()
        await raw.dispose()
