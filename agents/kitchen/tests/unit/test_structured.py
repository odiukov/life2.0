from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest
from kitchen.application.ports import HouseholdContext
from kitchen.application.schema import AddItem, OperationList
from kitchen.application.service import InventoryService, ItemAction
from kitchen.application.structured import DigestSkill, InventorySkill, ItemActionSkill, UndoSkill
from kitchen.domain.model import Category, Location, Source
from kitchen.domain.units import InputUnit
from kitchen.testing import KitchenMemory, in_memory_uow
from shared.a2a.request import SkillRequest
from shared.testing.fakes import FixedClock

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
A = UUID(int=1)


def req(params: dict[str, object]) -> SkillRequest:
    return SkillRequest(
        task_id=str(uuid4()),
        context_id="c",
        text="",
        user_id=A,
        skill_id="x",
        for_date=None,
        is_peer_call=False,
        params=params,
    )


async def seeded() -> tuple[InventoryService, UUID]:
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", {A: "Аня"}))
    svc = InventoryService(in_memory_uow(memory), FixedClock(NOW))
    result = await svc.apply(
        A,
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
                ),
                AddItem(
                    name="пельмени",
                    display_name="пельмени",
                    quantity=1,
                    unit=InputUnit.PACK,
                    location=Location.FREEZER,
                    category=Category.FROZEN,
                    shelf_life_days=90,
                ),
            ]
        ),
        refs={},
        source=Source.TEXT,
    )
    return svc, result.changes[0].after.pk


async def test_inventory_filters_by_location_and_names_the_author() -> None:
    svc, _ = await seeded()
    result = await InventorySkill(svc)(req({"location": "freezer"}), ())
    assert result.data is not None
    [item] = result.data["items"]  # type: ignore[misc]
    assert item["name"] == "пельмени"
    assert item["added_by"] == {"user_id": str(A), "name": "Аня"}
    assert item["quantity"] == "1.000"
    assert item["unit"] == "pack"


async def test_inventory_rejects_unknown_location() -> None:
    svc, _ = await seeded()
    result = await InventorySkill(svc)(req({"location": "garage"}), ())
    assert (result.failed, result.output) == (True, "invalid_params")


async def test_digest_buckets_by_household_local_date() -> None:
    svc, _ = await seeded()
    result = await DigestSkill(svc, FixedClock(NOW))(req({}), ())
    assert result.data is not None
    assert [i["name"] for i in result.data["tomorrow"]] == ["курица"]  # type: ignore[union-attr]
    assert result.data["expired"] == []
    assert result.data["today"] == []


async def test_item_action_then_undo_and_error_codes() -> None:
    svc, chicken = await seeded()
    action = ItemActionSkill(svc)
    moved = await action(
        req({"item_id": str(chicken), "action": "move", "location": "freezer"}), ()
    )
    assert moved.data is not None
    assert moved.data["item"]["location"] == "freezer"
    missing = await action(req({"item_id": str(chicken), "action": "move"}), ())
    assert (missing.failed, missing.output) == (True, "invalid_params")
    bogus = await action(req({"item_id": "nope", "action": "consumed"}), ())
    assert bogus.output == "invalid_params"
    gone = await action(req({"item_id": str(uuid4()), "action": "consumed"}), ())
    assert gone.output == "item_gone"
    undo = UndoSkill(svc)
    assert (await undo(req({"group_id": moved.data["group_id"]}), ())).data == {"outcome": "done"}  # type: ignore[index]
    again = await undo(req({"group_id": moved.data["group_id"]}), ())  # type: ignore[index]
    assert (again.failed, again.output) == (True, "already_undone")


@pytest.mark.parametrize("quantity", ["0", "-1", "abc"])
async def test_set_quantity_validation(quantity: str) -> None:
    svc, chicken = await seeded()
    result = await ItemActionSkill(svc)(
        req({"item_id": str(chicken), "action": "set_quantity", "quantity": quantity}), ()
    )
    assert result.output == "invalid_params"


@pytest.mark.parametrize("action", ["consumed", "discarded"])
async def test_inactive_action_returns_batch_and_cannot_repeat(action: str) -> None:
    svc, chicken = await seeded()
    result = await ItemActionSkill(svc)(req({"item_id": str(chicken), "action": action}), ())
    assert result.data is not None
    item = result.data["item"]
    assert isinstance(item, dict)
    assert item["id"] == str(chicken)
    assert set(item) == {
        "id",
        "name",
        "display_name",
        "category",
        "quantity",
        "unit",
        "location",
        "opened",
        "opened_on",
        "expires_on",
        "expiry_source",
        "added_at",
        "added_by",
    }
    inventory = await InventorySkill(svc)(req({}), ())
    assert inventory.data is not None
    assert all(i["id"] != str(chicken) for i in inventory.data["items"])  # type: ignore[union-attr]
    again = await ItemActionSkill(svc)(req({"item_id": str(chicken), "action": action}), ())
    assert (again.failed, again.output) == (True, "item_gone")


@pytest.mark.parametrize(
    ("action", "extra", "key", "value"),
    [
        ("opened", {}, "opened", True),
        ("set_expiry", {"expires_on": "2026-10-20"}, "expires_on", "2026-10-20"),
        ("set_quantity", {"quantity": "2.125"}, "quantity", "2.125"),
    ],
)
async def test_other_actions(
    action: str, extra: dict[str, object], key: str, value: object
) -> None:
    svc, chicken = await seeded()
    result = await ItemActionSkill(svc)(
        req({"item_id": str(chicken), "action": action, **extra}), ()
    )
    assert not result.failed
    assert result.data is not None
    assert result.data["item"][key] == value  # type: ignore[index]


@pytest.mark.parametrize(
    "params",
    [
        {},
        {"item_id": "missing"},
        {"action": "unknown"},
        {"action": "set_expiry"},
        {"action": "set_expiry", "expires_on": "2026-02-30"},
        {"action": "set_quantity"},
        {"action": "move", "location": []},
        {"action": "set_quantity", "quantity": "NaN"},
        {"action": "set_quantity", "quantity": "Infinity"},
        {"action": "set_quantity", "quantity": True},
        {"action": "set_quantity", "quantity": "0.0001"},
    ],
)
async def test_malformed_action_does_not_mutate(params: dict[str, object]) -> None:
    svc, chicken = await seeded()
    params = {"item_id": str(chicken), **params}
    before = await svc.snapshot(A)
    result = await ItemActionSkill(svc)(req(params), ())
    assert (result.failed, result.output) == (True, "invalid_params")
    assert await svc.snapshot(A) == before


async def test_undo_conflict_not_found_and_invalid_group() -> None:
    svc, chicken = await seeded()
    action = ItemActionSkill(svc)
    moved = await action(
        req({"item_id": str(chicken), "action": "move", "location": "freezer"}), ()
    )
    assert moved.data is not None
    await action(req({"item_id": str(chicken), "action": "opened"}), ())
    undo = UndoSkill(svc)
    conflict = await undo(req({"group_id": moved.data["group_id"]}), ())
    assert (conflict.failed, conflict.output) == (True, "conflict")
    assert (await undo(req({"group_id": str(uuid4())}), ())).output == "not_found"
    for params in ({}, {"group_id": "bad"}):
        assert (await undo(req(params), ())).output == "invalid_params"


@pytest.mark.parametrize("handler", ["inventory", "digest", "action", "undo"])
async def test_all_handlers_map_no_household(handler: str) -> None:
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", {}))
    svc = InventoryService(in_memory_uow(memory), FixedClock(NOW))
    handlers = {
        "inventory": InventorySkill(svc),
        "digest": DigestSkill(svc, FixedClock(NOW)),
        "action": ItemActionSkill(svc),
        "undo": UndoSkill(svc),
    }
    result = await handlers[handler](
        req({"item_id": str(uuid4()), "action": "consumed", "group_id": str(uuid4())}), ()
    )
    assert (result.failed, result.output) == (True, "no_household")


async def test_digest_local_midnight_boundaries_and_inactive_exclusion() -> None:
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", {A: "Anna"}))
    now = datetime(2026, 10, 13, 23, 30, tzinfo=UTC)
    svc = InventoryService(in_memory_uow(memory), FixedClock(now))
    created = await svc.apply(
        A,
        ops=OperationList(
            adds=[
                AddItem(
                    name=f"day{day}",
                    display_name=f"day{day}",
                    quantity=1,
                    unit=InputUnit.PCS,
                    location=Location.FRIDGE,
                    category=Category.OTHER,
                    expires_on=date(2026, 10, day),
                )
                for day in range(13, 19)
            ]
        ),
        refs={},
        source=Source.TEXT,
    )
    result = await DigestSkill(svc, FixedClock(now))(req({}), ())
    assert result.data is not None
    assert {k: [i["name"] for i in v] for k, v in result.data.items()} == {  # type: ignore[union-attr]
        "expired": ["day13"],
        "today": ["day14"],
        "tomorrow": ["day15"],
        "soon": ["day16", "day17"],
    }
    await svc.act(
        A,
        created.changes[0].after.pk,
        ItemAction.CONSUMED,
    )
    result = await DigestSkill(svc, FixedClock(now))(req({}), ())
    assert result.data is not None
    assert result.data["expired"] == []


async def test_action_keeps_committed_result_when_membership_changes_at_commit() -> None:
    from collections.abc import AsyncIterator
    from contextlib import asynccontextmanager
    from typing import cast

    from kitchen.testing import KitchenUowFactory, make_batch
    from shared.ports.uow import UnitOfWork

    members = {A: "Anna"}
    memory = KitchenMemory(HouseholdContext(UUID(int=9), "Europe/Lisbon", members))
    chicken = make_batch(id=1, added_by=A)
    memory.batches.rows[chicken.pk] = chicken

    class MembershipChangesAtCommit(KitchenUowFactory):
        transactions = 0

        def for_user(self, user_id: UUID) -> UnitOfWork:  # type: ignore[override]
            return cast(UnitOfWork, self.commit_then_remove(super().for_user(user_id)))

        @asynccontextmanager
        async def commit_then_remove(self, transaction: UnitOfWork) -> AsyncIterator[UnitOfWork]:
            self.transactions += 1
            async with transaction as uow:
                yield uow
            # Simulate the next lock owner removing membership after the write commits.
            members.clear()
            memory.context = None

    factory = MembershipChangesAtCommit(memory)
    svc = InventoryService(factory, FixedClock(NOW))
    result = await ItemActionSkill(svc)(req({"item_id": str(chicken.pk), "action": "consumed"}), ())
    assert not result.failed
    assert result.data is not None
    group_id = UUID(str(result.data["group_id"]))
    assert group_id in memory.log.groups
    assert memory.log.groups[group_id].changes[0].batch_id == chicken.pk
    assert result.data["item"]["added_by"] == {"user_id": str(A), "name": "Anna"}  # type: ignore[index]
    assert memory.batches.rows[chicken.pk].status.value == "consumed"
    assert factory.transactions == 1
    assert memory.context is None
