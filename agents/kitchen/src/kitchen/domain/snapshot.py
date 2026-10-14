"""JSON-safe snapshots of batches for the operation log (undo)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime
from decimal import Decimal
from uuid import UUID

from kitchen.domain.model import Batch, Category, ExpirySource, Location, Source, Status, Unit


def to_snapshot(batch: Batch) -> dict[str, object]:
    return {
        "id": str(batch.id) if batch.id else None,
        "name": batch.name,
        "display_name": batch.display_name,
        "category": batch.category.value,
        "quantity": str(batch.quantity),
        "unit": batch.unit.value,
        "location": batch.location.value,
        "status": batch.status.value,
        "opened": batch.opened,
        "opened_on": batch.opened_on.isoformat() if batch.opened_on else None,
        "added_at": batch.added_at.isoformat(),
        "added_by": str(batch.added_by) if batch.added_by else None,
        "expires_on": batch.expires_on.isoformat(),
        "expiry_source": batch.expiry_source.value,
        "next_check_on": batch.next_check_on.isoformat(),
        "source": batch.source.value,
    }


def _str(data: Mapping[str, object], key: str) -> str:
    return str(data[key])


def _opt_uuid(data: Mapping[str, object], key: str) -> UUID | None:
    value = data.get(key)
    return None if value is None else UUID(str(value))


def from_snapshot(data: Mapping[str, object]) -> Batch:
    opened_on = data.get("opened_on")
    return Batch(
        id=_opt_uuid(data, "id"),
        name=_str(data, "name"),
        display_name=_str(data, "display_name"),
        category=Category(_str(data, "category")),
        quantity=Decimal(_str(data, "quantity")),
        unit=Unit(_str(data, "unit")),
        location=Location(_str(data, "location")),
        status=Status(_str(data, "status")),
        opened=bool(data["opened"]),
        opened_on=date.fromisoformat(str(opened_on)) if opened_on else None,
        added_at=datetime.fromisoformat(_str(data, "added_at")),
        added_by=_opt_uuid(data, "added_by"),
        expires_on=date.fromisoformat(_str(data, "expires_on")),
        expiry_source=ExpirySource(_str(data, "expiry_source")),
        next_check_on=date.fromisoformat(_str(data, "next_check_on")),
        source=Source(_str(data, "source")),
    )
