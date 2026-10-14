from datetime import date, timedelta
from decimal import Decimal
from uuid import UUID

import pytest
from kitchen.domain.model import Status
from kitchen.domain.rules import fifo, set_quantity
from kitchen.domain.snapshot import from_snapshot, to_snapshot
from kitchen.testing import NOW, make_batch


def test_fifo_breaks_ties_by_insertion_time_not_uuid() -> None:
    later = make_batch(
        id=UUID(int=1), added_at=NOW + timedelta(minutes=5), expires_on=date(2026, 10, 18)
    )
    earlier = make_batch(id=UUID(int=2), added_at=NOW, expires_on=date(2026, 10, 18))
    assert fifo([later, earlier]) == [earlier, later]


def test_set_quantity_replaces_amount_in_batch_unit() -> None:
    batch = make_batch(id=1, quantity=Decimal("1000"))
    change = set_quantity(batch, Decimal("250.0004"))
    assert change.op_type == "update"
    assert change.after.quantity == Decimal("250.000")
    assert change.after.status is Status.ACTIVE
    assert batch.quantity == Decimal("1000")


@pytest.mark.parametrize("bad", [Decimal(0), Decimal(-1), Decimal("NaN"), Decimal("0.0001")])
def test_set_quantity_rejects_non_positive(bad: Decimal) -> None:
    with pytest.raises(ValueError, match="Quantity"):
        set_quantity(make_batch(id=1), bad)


def test_snapshot_round_trip_keeps_uuid_identity() -> None:
    batch = make_batch(id=7, added_by=3)
    assert from_snapshot(to_snapshot(batch)) == batch
    assert to_snapshot(batch)["id"] == str(UUID(int=7))
