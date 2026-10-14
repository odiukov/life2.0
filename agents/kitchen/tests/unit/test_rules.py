from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from kitchen.domain.model import (
    Category,
    ExpirySource,
    Location,
    Source,
    Status,
    Unit,
)
from kitchen.domain.rules import (
    IncompatibleUnits,
    NewBatch,
    NothingToConsume,
    add_batch,
    compute_next_check,
    consume,
    discard,
    fifo,
    mark_checked,
    normalize_name,
    set_expiry,
    update_batch,
)
from kitchen.domain.units import InputUnit
from kitchen.testing import NOW, TODAY, make_batch


def new(**overrides: object) -> NewBatch:
    values: dict[str, object] = {
        "name": "молоко",
        "display_name": "молоко",
        "category": Category.DAIRY,
        "quantity": Decimal("1000"),
        "unit": Unit.ML,
        "location": Location.FRIDGE,
        "opened": False,
        "expires_on": None,
        "shelf_life_days": 7,
        "opened_shelf_life_days": None,
        "source": Source.VOICE,
        "added_by": UUID(int=5),
    }
    values.update(overrides)
    return NewBatch(**values)  # type: ignore[arg-type]


def test_normalize_name() -> None:
    assert normalize_name("  Ёжик   В тумане ") == "ежик в тумане"


def test_next_check_is_day_before_for_estimates() -> None:
    assert compute_next_check(date(2026, 10, 20), ExpirySource.ESTIMATED) == date(2026, 10, 19)
    assert compute_next_check(date(2026, 10, 20), ExpirySource.EXPLICIT) == date(2026, 10, 20)
    assert compute_next_check(date(2026, 10, 20), ExpirySource.CORRECTED) == date(2026, 10, 20)


def test_add_estimates_expiry() -> None:
    change = add_batch([], new(), today=TODAY, now=NOW)
    assert change.before is None
    assert change.op_type == "add"
    batch = change.after
    assert batch.expires_on == TODAY + timedelta(days=7)
    assert batch.expiry_source is ExpirySource.ESTIMATED
    assert batch.next_check_on == TODAY + timedelta(days=6)
    assert (batch.added_by, batch.source, batch.status) == (
        UUID(int=5),
        Source.VOICE,
        Status.ACTIVE,
    )


def test_add_with_explicit_date() -> None:
    batch = add_batch([], new(expires_on=date(2026, 10, 16)), today=TODAY, now=NOW).after
    assert batch.expires_on == date(2026, 10, 16)
    assert batch.expiry_source is ExpirySource.EXPLICIT
    assert batch.next_check_on == date(2026, 10, 16)


def test_add_opened_uses_shorter_opened_life() -> None:
    batch = add_batch(
        [], new(opened=True, shelf_life_days=7, opened_shelf_life_days=3), today=TODAY, now=NOW
    ).after
    assert batch.opened
    assert batch.opened_on == TODAY
    assert batch.expires_on == TODAY + timedelta(days=3)


def test_add_without_any_shelf_life_uses_default() -> None:
    batch = add_batch([], new(shelf_life_days=None), today=TODAY, now=NOW).after
    assert batch.expires_on == TODAY + timedelta(days=7)


def test_add_merges_identical_closed_batch() -> None:
    existing = make_batch(id=3, expires_on=TODAY + timedelta(days=7))
    change = add_batch([existing], new(), today=TODAY, now=NOW)
    assert change.before == existing
    assert change.after.id == UUID(int=3)
    assert change.after.quantity == Decimal("2000")


def test_add_does_not_merge_different_expiry_or_opened() -> None:
    other_date = make_batch(id=3, expires_on=TODAY + timedelta(days=2))
    opened = make_batch(id=4, expires_on=TODAY + timedelta(days=7), opened=True)
    change = add_batch([other_date, opened], new(), today=TODAY, now=NOW)
    assert change.before is None


def test_fifo_orders_by_expiry_then_id() -> None:
    a = make_batch(id=2, expires_on=date(2026, 10, 18))
    b = make_batch(id=1, expires_on=date(2026, 10, 18))
    c = make_batch(id=3, expires_on=date(2026, 10, 15))
    gone = make_batch(id=4, expires_on=date(2026, 10, 14), status=Status.CONSUMED)
    assert [x.id for x in fifo([a, b, c, gone])] == [UUID(int=3), UUID(int=1), UUID(int=2)]


def test_consume_all_takes_earliest_batch() -> None:
    early = make_batch(id=1, expires_on=date(2026, 10, 15))
    late = make_batch(id=2, expires_on=date(2026, 10, 18))
    [change] = consume([late, early], quantity=None, unit=None)
    assert change.op_type == "consume"
    assert change.after.id == UUID(int=1)
    assert change.after.quantity == 0
    assert change.after.status is Status.CONSUMED


def test_consume_partial_with_conversion() -> None:
    batch = make_batch(id=1, quantity=Decimal("1000"))
    [change] = consume([batch], quantity=Decimal("0.5"), unit=InputUnit.L)
    assert change.after.quantity == Decimal("500")
    assert change.after.status is Status.ACTIVE


def test_consume_spills_over_batches() -> None:
    first = make_batch(id=1, expires_on=date(2026, 10, 15), quantity=Decimal("300"))
    second = make_batch(id=2, expires_on=date(2026, 10, 18), quantity=Decimal("1000"))
    changes = consume([first, second], quantity=Decimal("500"), unit=InputUnit.ML)
    assert [(c.after.id, c.after.quantity, c.after.status) for c in changes] == [
        (UUID(int=1), Decimal("0"), Status.CONSUMED),
        (UUID(int=2), Decimal("800"), Status.ACTIVE),
    ]


def test_consume_more_than_available_empties_everything() -> None:
    batch = make_batch(id=1, quantity=Decimal("200"))
    [change] = consume([batch], quantity=Decimal("1"), unit=InputUnit.L)
    assert change.after.status is Status.CONSUMED


def test_consume_incompatible_units() -> None:
    with pytest.raises(IncompatibleUnits):
        consume(
            [make_batch(id=1, unit=Unit.PCS, quantity=Decimal(3))],
            quantity=Decimal(200),
            unit=InputUnit.G,
        )


def test_consume_nothing() -> None:
    with pytest.raises(NothingToConsume):
        consume([make_batch(id=1, status=Status.DISCARDED)], quantity=None, unit=None)


def test_discard_takes_earliest() -> None:
    early = make_batch(id=1, expires_on=date(2026, 10, 15))
    change = discard([make_batch(id=2), early])
    assert (change.after.id, change.after.status, change.op_type) == (
        UUID(int=1),
        Status.DISCARDED,
        "discard",
    )


def test_open_prefers_closed_batch_and_shortens_expiry() -> None:
    opened = make_batch(id=1, opened=True, expires_on=date(2026, 10, 15))
    closed = make_batch(id=2, expires_on=date(2026, 10, 25))
    change = update_batch(
        [opened, closed],
        opened=True,
        location=None,
        expires_on=None,
        opened_shelf_life_days=4,
        today=TODAY,
    )
    assert change.after.id == UUID(int=2)
    assert change.after.opened_on == TODAY
    assert change.after.expires_on == TODAY + timedelta(days=4)
    assert change.after.expiry_source is ExpirySource.ESTIMATED
    assert change.after.next_check_on == TODAY + timedelta(days=3)


def test_open_never_extends_expiry() -> None:
    batch = make_batch(id=1, expires_on=date(2026, 10, 14))
    change = update_batch(
        [batch], opened=True, location=None, expires_on=None, opened_shelf_life_days=10, today=TODAY
    )
    assert change.after.expires_on == date(2026, 10, 14)


def test_move_and_explicit_expiry() -> None:
    batch = make_batch(id=1)
    change = update_batch(
        [batch],
        opened=None,
        location=Location.FREEZER,
        expires_on=date(2026, 12, 1),
        opened_shelf_life_days=None,
        today=TODAY,
    )
    assert change.after.location is Location.FREEZER
    assert change.after.expires_on == date(2026, 12, 1)
    assert change.after.expiry_source is ExpirySource.EXPLICIT
    assert change.after.next_check_on == date(2026, 12, 1)
    assert change.before == batch


def test_set_expiry_and_mark_checked() -> None:
    batch = make_batch(id=1)
    corrected = set_expiry(batch, date(2026, 10, 25), ExpirySource.CORRECTED).after
    assert (corrected.expires_on, corrected.next_check_on) == (
        date(2026, 10, 25),
        date(2026, 10, 25),
    )
    checked = mark_checked(batch, TODAY)
    assert checked.op_type == "check"
    assert checked.after.next_check_on == TODAY + timedelta(days=2)


@pytest.mark.parametrize(
    "overrides",
    [
        {"status": Status.CONSUMED},
        {"status": Status.DISCARDED},
        {"name": "cream"},
        {"unit": Unit.G},
        {"location": Location.FREEZER},
    ],
)
def test_add_keeps_distinct_batches_separate(overrides: dict[str, object]) -> None:
    change = add_batch([make_batch(id=3, **overrides)], new(), today=TODAY, now=NOW)
    assert change.before is None
    assert change.after.id is None


def test_add_opened_purchase_never_merges() -> None:
    existing = make_batch(id=3)
    change = add_batch([existing], new(opened=True), today=TODAY, now=NOW)
    assert change.before is None
    assert change.after.opened_on == TODAY


def test_merge_preserves_purchase_metadata_and_input() -> None:
    existing = make_batch(id=3, added_by=99, source=Source.TEXT)
    change = add_batch([existing], new(), today=TODAY, now=NOW)
    assert change.after is not existing
    assert existing.quantity == Decimal("1000")
    assert change.after.added_by == UUID(int=99)
    assert change.after.source is Source.TEXT
    assert change.after.added_at == existing.added_at


def test_add_uses_supplied_local_date_at_year_boundary() -> None:
    local_today = date(2027, 1, 1)
    batch = add_batch([], new(shelf_life_days=1), today=local_today, now=NOW).after
    assert batch.expires_on == date(2027, 1, 2)
    assert batch.next_check_on == local_today
    assert batch.added_at == NOW


def test_opened_shelf_life_does_not_extend_closed_life() -> None:
    batch = add_batch(
        [], new(opened=True, shelf_life_days=2, opened_shelf_life_days=8), today=TODAY, now=NOW
    ).after
    assert batch.expires_on == date(2026, 10, 15)


def test_opened_explicit_expiry_takes_precedence() -> None:
    batch = add_batch(
        [],
        new(opened=True, expires_on=date(2026, 10, 25), opened_shelf_life_days=1),
        today=TODAY,
        now=NOW,
    ).after
    assert batch.expires_on == date(2026, 10, 25)
    assert batch.expiry_source is ExpirySource.EXPLICIT


def test_consume_without_unit_uses_earliest_unit_and_skips_incompatible() -> None:
    first = make_batch(id=1, quantity=Decimal("0.125"), expires_on=date(2026, 10, 14))
    different = make_batch(id=2, unit=Unit.PACK, quantity=Decimal(3))
    second = make_batch(id=3, quantity=Decimal("0.875"))
    changes = consume([second, different, first], quantity=Decimal("0.5"), unit=None)
    assert [(c.after.id, c.after.quantity) for c in changes] == [
        (UUID(int=1), Decimal("0")),
        (UUID(int=3), Decimal("0.500")),
    ]
    assert first.quantity == Decimal("0.125")
    assert second.quantity == Decimal("0.875")
    assert different.quantity == Decimal(3)


@pytest.mark.parametrize(
    "action",
    [
        discard,
        lambda batches: update_batch(
            batches,
            opened=True,
            location=None,
            expires_on=None,
            opened_shelf_life_days=None,
            today=TODAY,
        ),
    ],
)
def test_mutation_selection_rejects_inactive_inventory(action: object) -> None:
    with pytest.raises(NothingToConsume):
        action([make_batch(status=Status.DISCARDED)])  # type: ignore[operator]


def test_close_clears_opened_on_and_preserves_check_schedule() -> None:
    batch = make_batch(id=1, opened=True, opened_on=TODAY, next_check_on=date(2026, 10, 22))
    change = update_batch(
        [batch],
        opened=False,
        location=None,
        expires_on=None,
        opened_shelf_life_days=None,
        today=TODAY,
    )
    assert not change.after.opened
    assert change.after.opened_on is None
    assert change.after.next_check_on == date(2026, 10, 22)
    assert batch.opened
    assert batch.opened_on == TODAY


def test_open_and_explicit_expiry_use_explicit_date() -> None:
    batch = make_batch(id=1)
    change = update_batch(
        [batch],
        opened=True,
        location=Location.FREEZER,
        expires_on=date(2026, 11, 2),
        opened_shelf_life_days=1,
        today=TODAY,
    )
    assert change.after.expires_on == date(2026, 11, 2)
    assert change.after.next_check_on == date(2026, 11, 2)
    assert change.after.expiry_source is ExpirySource.EXPLICIT
    assert change.after.opened_on == TODAY
    assert batch.expires_on == date(2026, 10, 20)
    assert not batch.opened


def test_reopening_does_not_reset_opened_on_or_check_schedule() -> None:
    batch = make_batch(
        id=1, opened=True, opened_on=date(2026, 10, 10), next_check_on=date(2026, 10, 23)
    )
    change = update_batch(
        [batch],
        opened=True,
        location=None,
        expires_on=None,
        opened_shelf_life_days=1,
        today=TODAY,
    )
    assert change.after == batch
    assert change.after is not batch


def test_discard_preserves_quantity_and_input_for_history() -> None:
    batch = make_batch(id=1)
    change = discard([batch])
    assert change.after.quantity == Decimal("1000")
    assert batch.status is Status.ACTIVE


def test_expiry_and_check_changes_preserve_original() -> None:
    batch = make_batch(id=1)
    updated = set_expiry(batch, date(2026, 11, 1), ExpirySource.ESTIMATED)
    checked = mark_checked(batch, date(2026, 12, 31))
    assert updated.after.next_check_on == date(2026, 10, 31)
    assert checked.after.next_check_on == date(2027, 1, 2)
    assert batch.expires_on == date(2026, 10, 20)
    assert batch.next_check_on == date(2026, 10, 19)


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "-Infinity", "0.0004"])
def test_add_rejects_unusable_quantity(quantity: str) -> None:
    existing = make_batch(id=1)
    with pytest.raises(ValueError, match="Quantity"):
        add_batch([existing], new(quantity=Decimal(quantity)), today=TODAY, now=NOW)
    assert existing.quantity == Decimal("1000")


@pytest.mark.parametrize("quantity", ["0", "-1", "NaN", "Infinity", "-Infinity", "0.0004"])
@pytest.mark.parametrize("unit", [None, InputUnit.ML])
def test_consume_rejects_unusable_quantity(quantity: str, unit: InputUnit | None) -> None:
    batch = make_batch(id=1)
    with pytest.raises(ValueError, match="Quantity"):
        consume([batch], quantity=Decimal(quantity), unit=unit)
    assert batch.quantity == Decimal("1000")


def test_add_and_unitless_consume_apply_storage_precision() -> None:
    batch = add_batch([], new(quantity=Decimal("1.2355")), today=TODAY, now=NOW).after
    assert batch.quantity == Decimal("1.236")
    [change] = consume([batch], quantity=Decimal("0.1255"), unit=None)
    assert change.after.quantity == Decimal("1.110")
    assert batch.quantity == Decimal("1.236")
