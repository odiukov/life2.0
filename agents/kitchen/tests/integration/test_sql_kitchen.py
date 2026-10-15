"""Household isolation, concurrency and join-move for kitchen tables (real Postgres)."""

import asyncio
import hashlib
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from kitchen.adapters.db import kitchen_uow
from kitchen.application.errors import NoHousehold
from kitchen.application.ports import BatchRepository, HouseholdView
from kitchen.application.schema import AddItem, OperationList
from kitchen.application.service import InventoryService, ItemAction, UndoOutcome
from kitchen.domain.model import Category, Location, Source
from kitchen.domain.units import InputUnit
from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.config import DatabaseSettings
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

pytestmark = pytest.mark.integration
MILK = AddItem(
    name="молоко",
    display_name="молоко",
    quantity=1,
    unit=InputUnit.L,
    location=Location.FRIDGE,
    category=Category.DAIRY,
    shelf_life_days=7,
)


async def as_user(engine: AsyncEngine, user: UUID, sql: str, **params: object) -> list[object]:
    async with engine.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(user)})
        return (
            list((await conn.execute(text(sql), params)).all())
            if sql.lstrip().upper().startswith("SELECT")
            else []
        )


@pytest.fixture
async def env(clean_db: PostgresUrls):  # type: ignore[no-untyped-def]
    raw = create_async_engine(clean_db.rw)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    yield raw, InventoryService(kitchen_uow(engine), SystemClock())
    await engine.dispose()
    await raw.dispose()


async def home(raw: AsyncEngine, user: UUID) -> None:
    await as_user(raw, user, "SELECT household_ensure('u', 'Europe/Lisbon')")


async def join(raw: AsyncEngine, owner: UUID, joiner: UUID, code: str) -> None:
    digest = hashlib.sha256(code.encode()).digest()
    async with raw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(owner)})
        await conn.execute(
            text(
                "INSERT INTO household_invites (code_hash, created_by, expires_at) VALUES (:h, :u, :e)"
            ),
            {"h": digest, "u": owner, "e": datetime.now(UTC) + timedelta(days=1)},
        )
    rows = await as_user(raw, joiner, "SELECT status FROM household_join(:h)", h=digest)
    assert rows[0][0] == "ok"  # type: ignore[index]


async def test_other_households_see_nothing(env) -> None:  # type: ignore[no-untyped-def]
    raw, svc = env
    a, c = uuid4(), uuid4()
    await home(raw, a)
    await home(raw, c)
    await svc.apply(a, ops=OperationList(adds=[MILK]), refs={}, source=Source.TEXT)
    _, theirs = await svc.snapshot(c)
    assert theirs == []
    rows = await as_user(raw, c, "SELECT count(*) FROM kitchen_batches")
    assert rows[0][0] == 0  # type: ignore[index]
    assert (await as_user(raw, c, "SELECT count(*) FROM kitchen_operation_groups"))[0][0] == 0  # type: ignore[index]


async def test_members_share_the_inventory(env) -> None:  # type: ignore[no-untyped-def]
    raw, svc = env
    a, b = uuid4(), uuid4()
    await home(raw, a)
    await home(raw, b)
    await join(raw, a, b, "SHARE1")
    await svc.apply(b, ops=OperationList(adds=[MILK]), refs={}, source=Source.TEXT)
    _, seen_by_a = await svc.snapshot(a)
    assert [x.name for x in seen_by_a] == ["молоко"]


async def test_sole_member_items_move_when_joining(env) -> None:  # type: ignore[no-untyped-def]
    raw, svc = env
    a, b = uuid4(), uuid4()
    await home(raw, a)
    await home(raw, b)
    await svc.apply(b, ops=OperationList(adds=[MILK]), refs={}, source=Source.TEXT)
    digest = hashlib.sha256(b"MOVE1").digest()
    async with raw.begin() as conn:
        await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
        await conn.execute(
            text(
                "INSERT INTO household_invites (code_hash, created_by, expires_at) VALUES (:h, :u, :e)"
            ),
            {"h": digest, "u": a, "e": datetime.now(UTC) + timedelta(days=1)},
        )
    preview = await as_user(
        raw, b, "SELECT items_to_move FROM household_invite_preview(:h)", h=digest
    )
    assert preview[0][0] == 1  # type: ignore[index]
    rows = await as_user(raw, b, "SELECT status FROM household_join(:h)", h=digest)
    assert rows[0][0] == "ok"  # type: ignore[index]
    _, seen_by_a = await svc.snapshot(a)
    assert [x.name for x in seen_by_a] == ["молоко"]


async def test_concurrent_actions_on_one_item_do_not_double_consume(env) -> None:  # type: ignore[no-untyped-def]
    raw, svc = env
    a, b = uuid4(), uuid4()
    await home(raw, a)
    await home(raw, b)
    await join(raw, a, b, "RACE1")
    added = await svc.apply(a, ops=OperationList(adds=[MILK]), refs={}, source=Source.TEXT)
    batch_id = added.changes[0].after.pk
    outcomes = await asyncio.gather(
        svc.act(a, batch_id, ItemAction.CONSUMED),
        svc.act(b, batch_id, ItemAction.CONSUMED),
        return_exceptions=True,
    )
    assert sorted(type(o).__name__ for o in outcomes) == ["ItemGone", "tuple"]
    rows = await as_user(raw, a, "SELECT count(*) FROM kitchen_operation_groups")
    assert rows[0][0] == 2  # type: ignore[index]  # the add and exactly one consume


async def test_undo_refuses_to_overwrite_another_member_change(env) -> None:
    raw, svc = env
    a, b = uuid4(), uuid4()
    await home(raw, a)
    await home(raw, b)
    await join(raw, a, b, "UNDO")
    added = await svc.apply(a, ops=OperationList(adds=[MILK]), refs={}, source=Source.TEXT)
    batch_id = added.changes[0].after.pk
    group, _ = await svc.act(b, batch_id, ItemAction.CONSUMED)
    assert await svc.undo(a, added.group_id) == UndoOutcome.CONFLICT
    assert await svc.undo(b, group) == UndoOutcome.DONE
    assert await svc.undo(a, added.group_id) == UndoOutcome.CONFLICT
    assert (await svc.snapshot(a))[1][0].quantity == 1000


async def test_lock_keeps_captured_household_and_rejects_moved_member(
    clean_db: PostgresUrls,
) -> None:
    raw = create_async_engine(clean_db.rw)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    a, b = uuid4(), uuid4()
    try:
        await home(raw, a)
        await home(raw, b)
        new = (await as_user(raw, a, "SELECT public.current_household_id()"))[0][0]

        async def lock_stale() -> None:
            async with kitchen_uow(engine).for_user(b) as uow:
                initial = await uow.repo(HouseholdView).current()
                assert initial is not None
                await join(raw, a, b, "CAPTURE")
                # Holding the NEW home proves lock() uses the captured OLD home.
                async with raw.begin() as holder:
                    await holder.execute(
                        text("SELECT public.household_lock(CAST(:h AS uuid))"), {"h": new}
                    )
                    await asyncio.wait_for(uow.repo(BatchRepository).lock(), timeout=2)

        with pytest.raises(NoHousehold):
            await lock_stale()
    finally:
        await engine.dispose()
        await raw.dispose()


async def test_scope_is_reset_between_pooled_transactions(clean_db: PostgresUrls) -> None:
    raw = create_async_engine(clean_db.rw)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw, "pool_size": 1}))
    a, b = uuid4(), uuid4()
    try:
        await home(raw, a)
        await home(raw, b)
        factory = kitchen_uow(engine)
        async with factory.for_user(b) as uow:
            old = await uow.repo(HouseholdView).current()
            await uow.repo(BatchRepository).lock()
        await join(raw, a, b, "POOL")
        async with factory.for_user(b) as uow:
            fresh = await uow.repo(HouseholdView).current()
            await uow.repo(BatchRepository).lock()
            assert old is not None
            assert fresh is not None
            assert old.household_id != fresh.household_id
    finally:
        await engine.dispose()
        await raw.dispose()


async def test_digest_discovery_local_date_claim_and_privileges(clean_db: PostgresUrls) -> None:
    raw = create_async_engine(clean_db.rw)
    admin = create_async_engine(clean_db.admin)
    a, b = uuid4(), uuid4()
    try:
        await home(raw, a)
        await home(raw, b)
        await join(raw, a, b, "DIGEST")
        await as_user(
            raw,
            a,
            "SELECT public.household_update(NULL::text, 'America/Los_Angeles'::text, '18:00'::time)",
        )
        now = datetime(2026, 10, 15, 2, 30, tzinfo=UTC)  # Oct 14, 19:30 in the household.
        rows = await as_user(
            raw, a, "SELECT * FROM public.kitchen_digests_due(CAST(:now AS timestamptz))", now=now
        )
        assert len(rows) == 1
        row = rows[0]
        assert row.owner_id == a
        assert set(row.member_ids) == {a, b}
        assert row.local_date.isoformat() == "2026-10-14"
        async with raw.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
            await conn.execute(
                text("INSERT INTO kitchen_digest_runs(local_date) VALUES (:d)"),
                {"d": row.local_date},
            )
        assert (
            await as_user(
                raw,
                a,
                "SELECT * FROM public.kitchen_digests_due(CAST(:now AS timestamptz))",
                now=now,
            )
            == []
        )
        async with admin.connect() as conn:
            privileges = (
                await conn.execute(
                    text(
                        "SELECT prosecdef, proconfig, "
                        "has_function_privilege('app_rw', oid, 'EXECUTE') AS rw, "
                        "EXISTS (SELECT 1 FROM aclexplode(COALESCE(proacl, acldefault('f', proowner))) a "
                        "WHERE a.grantee NOT IN (proowner, (SELECT oid FROM pg_roles WHERE rolname = 'app_rw'))) AS unexpected_grant "
                        "FROM pg_proc WHERE oid = 'public.kitchen_digests_due(timestamptz)'::regprocedure"
                    )
                )
            ).one()
            assert privileges.prosecdef
            assert privileges.rw
            assert not privileges.unexpected_grant
            assert privileges.proconfig == ["search_path=public, pg_temp"]
            for name in (
                "kitchen_batches",
                "kitchen_operation_groups",
                "kitchen_clarifications",
                "kitchen_digest_runs",
            ):
                flags = (
                    await conn.execute(
                        text(
                            "SELECT relrowsecurity, relforcerowsecurity, "
                            "EXISTS (SELECT 1 FROM information_schema.role_table_grants "
                            "WHERE table_schema = 'public' AND table_name = :name "
                            "AND grantee NOT IN ('app_owner', 'app_rw', current_user)) AS unexpected_grant "
                            "FROM pg_class WHERE relname = :name"
                        ),
                        {"name": name},
                    )
                ).one()
                assert flags.relrowsecurity
                assert not flags.relforcerowsecurity
                assert not flags.unexpected_grant
    finally:
        await raw.dispose()
        await admin.dispose()


async def test_membership_move_waits_for_kitchen_transaction(clean_db: PostgresUrls) -> None:
    raw = create_async_engine(clean_db.rw)
    admin = create_async_engine(clean_db.admin)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    a, b = uuid4(), uuid4()
    movement = None
    try:
        await home(raw, a)
        await home(raw, b)
        svc = InventoryService(kitchen_uow(engine), SystemClock())
        added = await svc.apply(b, ops=OperationList(adds=[MILK]), refs={}, source=Source.TEXT)
        waiter_pid: asyncio.Future[int] = asyncio.get_running_loop().create_future()
        digest = hashlib.sha256(b"SERIAL").digest()
        async with raw.begin() as conn:
            await conn.execute(text("SELECT set_config('app.user_id', :u, true)"), {"u": str(a)})
            await conn.execute(
                text(
                    "INSERT INTO household_invites (code_hash, created_by, expires_at) VALUES (:h, :u, :e)"
                ),
                {"h": digest, "u": a, "e": datetime.now(UTC) + timedelta(days=1)},
            )

        async def move() -> str:
            async with raw.begin() as conn:
                await conn.execute(
                    text("SELECT set_config('app.user_id', :u, true)"), {"u": str(b)}
                )
                waiter_pid.set_result(
                    (await conn.execute(text("SELECT pg_backend_pid()"))).scalar_one()
                )
                return (
                    await conn.execute(
                        text("SELECT status FROM public.household_join(:h)"), {"h": digest}
                    )
                ).scalar_one()

        async def wait_until_blocked(pid: int) -> None:
            async with admin.connect() as conn:
                while True:
                    event = (
                        await conn.execute(
                            text("SELECT wait_event FROM pg_stat_activity WHERE pid = :pid"),
                            {"pid": pid},
                        )
                    ).scalar_one_or_none()
                    await conn.commit()  # Refresh PostgreSQL's activity snapshot on the next poll.
                    if event == "advisory":
                        return
                    await asyncio.sleep(0.01)

        async with kitchen_uow(engine).for_user(b) as uow:
            await uow.repo(HouseholdView).current()
            await uow.repo(BatchRepository).lock()
            movement = asyncio.create_task(move())
            pid = await asyncio.wait_for(waiter_pid, 2)
            await asyncio.wait_for(wait_until_blocked(pid), 2)
            assert not movement.done()
            assert (await uow.repo(BatchRepository).get(added.changes[0].after.pk)) is not None
        assert await asyncio.wait_for(movement, 5) == "ok"
        assert [batch.pk for batch in (await svc.snapshot(a))[1]] == [added.changes[0].after.pk]
        # Operation groups moved too, so the original actor can undo in the new home.
        assert await svc.undo_last(b) == UndoOutcome.DONE
    finally:
        if movement is not None and not movement.done():
            movement.cancel()
            await asyncio.gather(movement, return_exceptions=True)
        await engine.dispose()
        await raw.dispose()
        await admin.dispose()


@pytest.mark.parametrize("operation", ["context", "snapshot", "apply", "act", "undo", "undo_last"])
async def test_no_membership_rejects_every_service_operation(env, operation: str) -> None:
    _, svc = env
    actor = uuid4()

    async def invoke() -> None:
        if operation == "apply":
            await svc.apply(actor, ops=OperationList(adds=[MILK]), refs={}, source=Source.TEXT)
        elif operation == "act":
            await svc.act(actor, uuid4(), ItemAction.CONSUMED)
        elif operation == "undo":
            await svc.undo(actor, uuid4())
        else:
            await getattr(svc, operation)(actor)

    with pytest.raises(NoHousehold):
        await invoke()
