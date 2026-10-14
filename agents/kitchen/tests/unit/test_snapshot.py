import json
from datetime import date
from decimal import Decimal
from uuid import UUID

from kitchen.domain.snapshot import from_snapshot, to_snapshot
from kitchen.testing import NOW, make_batch


def test_roundtrip_through_json() -> None:
    batch = make_batch(id=9, opened=True, opened_on=date(2026, 10, 13), added_by=4)
    data = json.loads(json.dumps(to_snapshot(batch)))
    assert from_snapshot(data) == batch


def test_roundtrip_with_nulls() -> None:
    batch = make_batch(id=1)
    assert from_snapshot(json.loads(json.dumps(to_snapshot(batch)))) == batch


def test_snapshot_keeps_decimal_precision_and_calendar_dates() -> None:
    batch = make_batch(
        id=None,
        quantity=Decimal("123456789012345.000001"),
        added_at=NOW,
        expires_on=date(2027, 1, 1),
        next_check_on=date(2026, 12, 31),
    )
    data = to_snapshot(batch)
    assert data["quantity"] == "123456789012345.000001"
    assert data["expires_on"] == "2027-01-01"
    assert data["next_check_on"] == "2026-12-31"
    assert data["added_at"] == "2026-10-13T12:00:00+00:00"
    assert data["id"] is None
    restored = from_snapshot(json.loads(json.dumps(data)))
    assert restored == batch
    assert restored.added_at.tzinfo == NOW.tzinfo


def test_consumed_snapshot_restores_typed_enums_and_zero_quantity() -> None:
    from kitchen.domain.model import (
        Category,
        ExpirySource,
        Location,
        Source,
        Status,
        Unit,
    )

    batch = make_batch(
        id=8,
        category=Category.FROZEN,
        unit=Unit.PACK,
        location=Location.FREEZER,
        quantity=Decimal(0),
        status=Status.CONSUMED,
        expiry_source=ExpirySource.CORRECTED,
        source=Source.VOICE,
    )
    data = json.loads(json.dumps(to_snapshot(batch)))
    assert (
        data["category"],
        data["unit"],
        data["location"],
        data["status"],
        data["expiry_source"],
        data["source"],
        data["quantity"],
    ) == (
        "frozen",
        "pack",
        "freezer",
        "consumed",
        "corrected",
        "voice",
        "0",
    )
    restored = from_snapshot(data)
    assert restored == batch
    assert restored.status is Status.CONSUMED
    assert restored.expiry_source is ExpirySource.CORRECTED
    assert restored.source is Source.VOICE
    assert restored.pk == UUID(int=8)
