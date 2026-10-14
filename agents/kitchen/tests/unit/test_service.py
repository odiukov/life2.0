from datetime import UTC, date, datetime
from decimal import Decimal
from uuid import UUID, uuid4

import pytest
from kitchen.application.errors import ItemGone, NoHousehold
from kitchen.application.ports import HouseholdContext
from kitchen.application.schema import AddItem, ConsumeItem, DiscardItem, OperationList, UpdateItem
from kitchen.application.service import (
    ApplyNeedsClarification,
    InventoryService,
    ItemAction,
    UndoOutcome,
)
from kitchen.domain.model import Category, Location, Source, Status, Unit
from kitchen.domain.units import InputUnit
from kitchen.testing import KitchenMemory, in_memory_uow
from shared.testing.fakes import FixedClock

HOME = UUID(int=100)
A, B = UUID(int=1), UUID(int=2)
NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


def env(
    now: datetime = NOW, timezone: str = "Europe/Lisbon"
) -> tuple[InventoryService, KitchenMemory, FixedClock]:
    memory = KitchenMemory(HouseholdContext(HOME, timezone, {A: "Аня", B: "Боря"}))
    clock = FixedClock(now)
    return InventoryService(in_memory_uow(memory), clock), memory, clock


def milk(**kw: object) -> AddItem:
    values: dict[str, object] = {
        "name": "молоко",
        "display_name": "молоко 3.2%",
        "quantity": 1,
        "unit": InputUnit.L,
        "location": Location.FRIDGE,
        "category": Category.DAIRY,
        "shelf_life_days": 7,
    }
    values.update(kw)
    return AddItem.model_validate(values)


async def test_apply_adds_and_records_one_group() -> None:
    svc, memory, _ = env()
    result = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    [change] = result.changes
    assert (change.op_type, change.after.quantity, change.after.unit) == (
        "add",
        Decimal("1000.000"),
        Unit.ML,
    )
    assert change.after.added_by == A
    group = memory.log.groups[result.group_id]
    assert group.user_id == A
    assert [c.op_type for c in group.changes] == ["add"]


async def test_today_uses_household_timezone() -> None:
    # 23:30 UTC on Oct 13 is already Oct 14 in Moscow (UTC+3).
    svc, _, _ = env(datetime(2026, 10, 13, 23, 30, tzinfo=UTC), "Europe/Moscow")
    result = await svc.apply(
        A, ops=OperationList(adds=[milk(shelf_life_days=3)]), refs={}, source=Source.TEXT
    )
    assert result.changes[0].after.expires_on == date(2026, 10, 17)


async def test_consume_partial_then_full_by_reference() -> None:
    svc, _, _ = env()
    await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    half = OperationList(consumes=[ConsumeItem(item_ref="молочко", quantity=0.5, unit=InputUnit.L)])
    result = await svc.apply(B, ops=half, refs={"молочко": "молоко"}, source=Source.TEXT)
    assert result.changes[0].after.quantity == Decimal("500.000")
    done = await svc.apply(
        B,
        ops=OperationList(consumes=[ConsumeItem(item_ref="молоко")]),
        refs={"молоко": "молоко"},
        source=Source.TEXT,
    )
    assert done.changes[0].after.status is Status.CONSUMED
    _, active = await svc.snapshot(A)
    assert active == []


async def test_incompatible_units_need_clarification_and_roll_back() -> None:
    svc, memory, _ = env()
    await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    ops = OperationList(
        adds=[milk(name="хлеб", display_name="хлеб", unit=InputUnit.PCS, category=Category.BAKERY)],
        consumes=[ConsumeItem(item_ref="молоко", quantity=2, unit=InputUnit.PCS)],
    )
    with pytest.raises(ApplyNeedsClarification) as error:
        await svc.apply(A, ops=ops, refs={"молоко": "молоко"}, source=Source.TEXT)
    assert (error.value.ref, error.value.reason) == ("молоко", "incompatible_units")
    _, active = await svc.snapshot(A)
    assert [b.name for b in active] == ["молоко"]  # the bread was not kept
    assert len(memory.log.groups) == 1


async def test_act_on_item_and_item_gone() -> None:
    svc, _, _ = env()
    added = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    batch_id = added.changes[0].after.pk
    _group, after = await svc.act(B, batch_id, ItemAction.MOVE, location=Location.FREEZER)
    assert after is not None
    assert after.location is Location.FREEZER
    _, eaten = await svc.act(B, batch_id, ItemAction.CONSUMED)
    assert eaten is not None
    assert eaten.status is Status.CONSUMED
    with pytest.raises(ItemGone):
        await svc.act(A, batch_id, ItemAction.DISCARDED)
    with pytest.raises(ItemGone):
        await svc.act(A, uuid4(), ItemAction.CONSUMED)


async def test_undo_restores_and_refuses_after_a_later_change() -> None:
    svc, _, _ = env()
    added = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    batch_id = added.changes[0].after.pk
    eaten_group, _ = await svc.act(B, batch_id, ItemAction.CONSUMED)
    assert await svc.undo(A, added.group_id) is UndoOutcome.CONFLICT  # review focus 3
    assert await svc.undo(B, eaten_group) is UndoOutcome.DONE
    assert await svc.undo(B, eaten_group) is UndoOutcome.ALREADY_UNDONE
    _, active = await svc.snapshot(A)
    assert [b.status for b in active] == [Status.ACTIVE]
    assert (
        await svc.undo(A, added.group_id) is UndoOutcome.CONFLICT
    )  # the undo itself was a later change
    assert await svc.undo(A, uuid4()) is UndoOutcome.NOT_FOUND


async def test_undo_of_an_add_removes_the_batch() -> None:
    svc, _, _ = env()
    added = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    assert await svc.undo(A, added.group_id) is UndoOutcome.DONE
    _, active = await svc.snapshot(A)
    assert active == []


async def test_update_and_discard_and_set_quantity() -> None:
    svc, _, _ = env()
    await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    opened = await svc.apply(
        A,
        ops=OperationList(
            updates=[UpdateItem(item_ref="молоко", opened=True, opened_shelf_life_days=3)]
        ),
        refs={"молоко": "молоко"},
        source=Source.TEXT,
    )
    assert opened.changes[0].after.opened is True
    batch_id = opened.changes[0].after.pk
    _, after = await svc.act(A, batch_id, ItemAction.SET_QUANTITY, quantity=Decimal("250"))
    assert after is not None
    assert after.quantity == Decimal("250.000")
    gone = await svc.apply(
        A,
        ops=OperationList(discards=[DiscardItem(item_ref="молоко")]),
        refs={"молоко": "молоко"},
        source=Source.TEXT,
    )
    assert gone.changes[0].after.status is Status.DISCARDED


OPERATIONS = ["context", "snapshot", "apply", "act", "undo"]


async def invoke(svc: InventoryService, operation: str, batch_id: UUID) -> object:
    if operation == "context":
        return await svc.context(A)
    if operation == "snapshot":
        return await svc.snapshot(A)
    if operation == "apply":
        return await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    if operation == "act":
        return await svc.act(A, batch_id, ItemAction.CONSUMED)
    return await svc.undo(A, batch_id)


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize("context", [None, HouseholdContext(HOME, "UTC", {B: "Bob"})])
async def test_without_membership_everything_is_no_household(operation, context) -> None:
    memory = KitchenMemory(context)
    svc = InventoryService(in_memory_uow(memory), FixedClock(NOW))
    with pytest.raises(NoHousehold):
        await invoke(svc, operation, uuid4())
    assert memory.batches.rows == {}
    assert memory.log.groups == {}
    assert memory.batches.locks == 0


@pytest.mark.parametrize("operation", OPERATIONS)
@pytest.mark.parametrize(
    "after",
    [
        None,
        HouseholdContext(UUID(int=101), "UTC", {A: "Ann"}),
        HouseholdContext(HOME, "UTC", {B: "Bob"}),
    ],
)
async def test_revalidate_context_after_lock_before_any_operation(operation, after) -> None:
    from kitchen.application.ports import HouseholdView

    class MovingView:
        calls = 0

        async def current(self):
            self.calls += 1
            return HouseholdContext(HOME, "UTC", {A: "Ann"}) if self.calls == 1 else after

    memory = KitchenMemory(HouseholdContext(HOME, "UTC", {A: "Ann"}))
    memory.extra[HouseholdView] = MovingView()
    svc = InventoryService(in_memory_uow(memory), FixedClock(NOW))
    with pytest.raises(NoHousehold):
        await invoke(svc, operation, uuid4())
    assert memory.batches.rows == {}
    assert memory.log.groups == {}
    assert memory.batches.locks == 1


async def test_context_and_snapshot_lock_and_use_refreshed_timezone() -> None:
    from kitchen.application.ports import HouseholdView

    class RefreshingView:
        calls = 0

        async def current(self):
            self.calls += 1
            zone = "UTC" if self.calls % 2 else "Europe/Moscow"
            return HouseholdContext(HOME, zone, {A: "Ann"})

    memory = KitchenMemory(HouseholdContext(HOME, "UTC", {A: "Ann"}))
    memory.extra[HouseholdView] = RefreshingView()
    svc = InventoryService(in_memory_uow(memory), FixedClock(NOW))
    assert (await svc.context(A)).timezone == "Europe/Moscow"
    assert (await svc.snapshot(A))[0].timezone == "Europe/Moscow"
    assert memory.batches.locks == 2


async def test_memory_view_observes_membership_change_between_transactions() -> None:
    svc, memory, _ = env()
    assert (await svc.context(A)).household_id == HOME
    memory.context = None
    with pytest.raises(NoHousehold):
        await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    assert memory.batches.rows == {}
    assert memory.log.groups == {}


async def test_concurrent_actions_on_one_item_do_not_double_consume() -> None:
    import asyncio

    svc, memory, _ = env()
    added = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    batch_id = added.changes[0].after.pk
    results = await asyncio.gather(
        svc.act(A, batch_id, ItemAction.CONSUMED),
        svc.act(B, batch_id, ItemAction.CONSUMED),
        return_exceptions=True,
    )
    assert sum(isinstance(result, ItemGone) for result in results) == 1
    assert len(memory.log.groups) == 2
    assert memory.batches.rows[batch_id].quantity == 0
    assert memory.batches.rows[batch_id].status is Status.CONSUMED


async def test_waiting_clarification_rollback_preserves_committed_writer() -> None:
    import asyncio

    svc, memory, _ = env()
    results = await asyncio.gather(
        svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT),
        svc.apply(
            B,
            ops=OperationList(
                adds=[milk(name="bread", display_name="bread")],
                consumes=[ConsumeItem(item_ref="молоко", quantity=2, unit=InputUnit.PCS)],
            ),
            refs={"молоко": "молоко"},
            source=Source.TEXT,
        ),
        return_exceptions=True,
    )
    assert isinstance(results[1], ApplyNeedsClarification)
    assert [b.name for b in memory.batches.rows.values()] == ["молоко"]
    assert len(memory.log.groups) == 1


@pytest.mark.parametrize(
    ("action", "kwargs"),
    [
        (ItemAction.MOVE, {}),
        (ItemAction.SET_EXPIRY, {}),
        (ItemAction.SET_QUANTITY, {}),
        (ItemAction.SET_QUANTITY, {"quantity": Decimal("-1")}),
        (ItemAction.SET_QUANTITY, {"quantity": Decimal("NaN")}),
        (ItemAction.SET_QUANTITY, {"quantity": Decimal("0.0001")}),
    ],
)
async def test_invalid_actions_do_not_write(action, kwargs) -> None:
    from kitchen.application.errors import InvalidAction

    svc, memory, _ = env()
    added = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    before = memory.batches.checkpoint()
    with pytest.raises(InvalidAction):
        await svc.act(A, added.changes[0].after.pk, action, **kwargs)
    assert memory.batches.checkpoint() == before
    assert len(memory.log.groups) == 1


async def test_undo_multiple_changes_of_same_batch_restores_original() -> None:
    svc, memory, _ = env()
    added = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    group = await svc.apply(
        B,
        ops=OperationList(
            updates=[UpdateItem(item_ref="молоко", opened=True)],
            consumes=[ConsumeItem(item_ref="молоко", quantity=0.25, unit=InputUnit.L)],
        ),
        refs={"молоко": "молоко"},
        source=Source.TEXT,
    )
    assert await svc.undo(A, group.group_id) is UndoOutcome.DONE
    restored = memory.batches.rows[added.changes[0].after.pk]
    assert restored.quantity == Decimal("1000.000")
    assert restored.opened is False
    assert await svc.undo(A, added.group_id) is UndoOutcome.CONFLICT


@pytest.mark.parametrize("resolved", [False, True])
async def test_mixed_valid_and_missing_references_commit_valid_operations(resolved) -> None:
    svc, memory, _ = env()
    refs = {"missing": "missing"} if resolved else {}
    result = await svc.apply(
        A,
        ops=OperationList(
            adds=[milk(name="bread", display_name="bread")],
            updates=[UpdateItem(item_ref="missing", opened=True)],
            consumes=[ConsumeItem(item_ref="missing")],
            discards=[DiscardItem(item_ref="missing")],
        ),
        refs=refs,
        source=Source.TEXT,
    )
    assert result.not_found == ["missing"]
    assert [change.op_type for change in result.changes] == ["add"]
    assert [batch.name for batch in memory.batches.rows.values()] == ["bread"]
    assert [change.op_type for change in memory.log.groups[result.group_id].changes] == ["add"]


@pytest.mark.parametrize("action", [ItemAction.CONSUMED, ItemAction.DISCARDED])
async def test_reference_becomes_inactive_before_waiting_apply_locks(action, monkeypatch) -> None:
    import asyncio

    svc, memory, _ = env()
    purchase = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    batch_id = purchase.changes[0].after.pk
    _, snapshot = await svc.snapshot(B)
    assert [batch.name for batch in snapshot] == ["молоко"]

    acquired = asyncio.Event()
    release = asyncio.Event()
    original_lock = memory.batches.lock

    async def pause_first_writer():
        await original_lock()
        if not acquired.is_set():
            acquired.set()
            await release.wait()

    monkeypatch.setattr(memory.batches, "lock", pause_first_writer)
    action_task = asyncio.create_task(svc.act(A, batch_id, action))
    await acquired.wait()
    apply_task = asyncio.create_task(
        svc.apply(
            B,
            ops=OperationList(
                adds=[milk(name="bread", display_name="bread")],
                consumes=[ConsumeItem(item_ref="milk")],
            ),
            refs={"milk": snapshot[0].name},
            source=Source.TEXT,
        )
    )
    await asyncio.sleep(0)
    release.set()
    await action_task
    result = await apply_task
    assert result.not_found == ["milk"]
    assert [change.op_type for change in result.changes] == ["add"]
    assert memory.batches.rows[batch_id].status is not Status.ACTIVE
    _, active = await svc.snapshot(B)
    assert [batch.name for batch in active] == ["bread"]
    assert len(memory.log.groups) == 3


async def test_reference_deleted_after_snapshot_is_skipped_under_lock() -> None:
    from kitchen.application.ports import BatchRepository

    svc, memory, _ = env()
    purchase = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    _, snapshot = await svc.snapshot(B)
    async with in_memory_uow(memory).for_user(A) as uow:
        batches = uow.repo(BatchRepository)
        await batches.lock()
        await batches.delete(purchase.changes[0].after.pk)
    result = await svc.apply(
        B,
        ops=OperationList(
            adds=[milk(name="bread", display_name="bread")],
            consumes=[ConsumeItem(item_ref="milk")],
        ),
        refs={"milk": snapshot[0].name},
        source=Source.TEXT,
    )
    assert result.not_found == ["milk"]
    assert [batch.name for batch in memory.batches.rows.values()] == ["bread"]


async def test_later_references_exhausted_within_same_list_are_reported_once() -> None:
    svc, memory, _ = env()
    purchase = await svc.apply(A, ops=OperationList(adds=[milk()]), refs={}, source=Source.TEXT)
    result = await svc.apply(
        B,
        ops=OperationList(
            adds=[milk(name="bread", display_name="bread")],
            consumes=[ConsumeItem(item_ref="milk"), ConsumeItem(item_ref="milk")],
            discards=[DiscardItem(item_ref="milk")],
        ),
        refs={"milk": "молоко"},
        source=Source.TEXT,
    )
    assert result.not_found == ["milk"]
    assert [change.op_type for change in result.changes] == ["add", "consume"]
    assert memory.batches.rows[purchase.changes[0].after.pk].quantity == 0
    assert memory.batches.rows[purchase.changes[0].after.pk].status is Status.CONSUMED
    assert len(memory.log.groups) == 2


async def test_all_missing_references_create_no_group_and_deduplicate_in_order() -> None:
    svc, memory, _ = env()
    result = await svc.apply(
        A,
        ops=OperationList(
            updates=[UpdateItem(item_ref="first", opened=True)],
            consumes=[ConsumeItem(item_ref="second"), ConsumeItem(item_ref="first")],
            discards=[DiscardItem(item_ref="second")],
        ),
        refs={"first": "first", "second": "second"},
        source=Source.TEXT,
    )
    assert result.not_found == ["first", "second"]
    assert result.changes == []
    assert memory.batches.rows == {}
    assert memory.log.groups == {}
