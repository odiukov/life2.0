"""Inventory rules. Pure functions: they compute changes, callers persist them."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
from decimal import Decimal
from uuid import UUID

from kitchen.domain.model import Batch, Category, ExpirySource, Location, Source, Status, Unit
from kitchen.domain.units import InputUnit, normalize_quantity

DEFAULT_SHELF_LIFE_DAYS = 7
CHECK_AGAIN_AFTER = timedelta(days=2)
_THOUSANDTH = Decimal("0.001")


class IncompatibleUnits(Exception):
    """The requested quantity cannot be expressed in the batch's unit."""


class NothingToConsume(Exception):
    """No active batch matches."""


@dataclass(frozen=True, slots=True)
class NewBatch:
    name: str
    display_name: str
    category: Category
    quantity: Decimal
    unit: Unit
    location: Location
    opened: bool
    expires_on: date | None
    shelf_life_days: int | None
    opened_shelf_life_days: int | None
    source: Source
    added_by: UUID | None


@dataclass(frozen=True, slots=True)
class Change:
    op_type: str
    before: Batch | None
    after: Batch


def normalize_name(name: str) -> str:
    return " ".join(name.lower().replace("ё", "е").split())


def fifo(batches: Sequence[Batch]) -> list[Batch]:
    active = [b for b in batches if b.status is Status.ACTIVE]
    return sorted(active, key=lambda b: (b.expires_on, b.added_at, str(b.id)))


def compute_next_check(expires_on: date, source: ExpirySource) -> date:
    if source is ExpirySource.ESTIMATED:
        return expires_on - timedelta(days=1)
    return expires_on


def add_batch(active: Sequence[Batch], new: NewBatch, *, today: date, now: datetime) -> Change:
    quantity, _ = normalize_quantity(new.quantity, new.unit)
    if new.expires_on is not None:
        expires_on, source = new.expires_on, ExpirySource.EXPLICIT
    else:
        days = new.shelf_life_days if new.shelf_life_days is not None else DEFAULT_SHELF_LIFE_DAYS
        expires_on, source = today + timedelta(days=days), ExpirySource.ESTIMATED
        if new.opened and new.opened_shelf_life_days is not None:
            expires_on = min(expires_on, today + timedelta(days=new.opened_shelf_life_days))
    if not new.opened:
        for existing in active:
            if (
                existing.status is Status.ACTIVE
                and not existing.opened
                and (existing.name, existing.unit, existing.location, existing.expires_on)
                == (new.name, new.unit, new.location, expires_on)
            ):
                merged = replace(existing, quantity=existing.quantity + quantity)
                return Change("add", existing, merged)
    batch = Batch(
        id=None,
        name=new.name,
        display_name=new.display_name,
        category=new.category,
        quantity=quantity,
        unit=new.unit,
        location=new.location,
        status=Status.ACTIVE,
        opened=new.opened,
        opened_on=today if new.opened else None,
        added_at=now,
        added_by=new.added_by,
        expires_on=expires_on,
        expiry_source=source,
        next_check_on=compute_next_check(expires_on, source),
        source=new.source,
    )
    return Change("add", None, batch)


def consume(
    batches: Sequence[Batch], *, quantity: Decimal | None, unit: InputUnit | None
) -> list[Change]:
    ordered = fifo(batches)
    if not ordered:
        raise NothingToConsume
    if quantity is None:
        first = ordered[0]
        return [
            Change("consume", first, replace(first, quantity=Decimal(0), status=Status.CONSUMED))
        ]
    amount, base = normalize_quantity(quantity, unit if unit is not None else ordered[0].unit)
    compatible = [b for b in ordered if b.unit is base]
    if not compatible:
        raise IncompatibleUnits
    changes: list[Change] = []
    remaining = amount
    for batch in compatible:
        if remaining <= 0:
            break
        taken = min(remaining, batch.quantity)
        left = batch.quantity - taken
        status = Status.CONSUMED if left <= 0 else Status.ACTIVE
        changes.append(
            Change("consume", batch, replace(batch, quantity=max(left, Decimal(0)), status=status))
        )
        remaining -= taken
    return changes


def discard(batches: Sequence[Batch]) -> Change:
    ordered = fifo(batches)
    if not ordered:
        raise NothingToConsume
    return Change("discard", ordered[0], replace(ordered[0], status=Status.DISCARDED))


def update_batch(
    batches: Sequence[Batch],
    *,
    opened: bool | None,
    location: Location | None,
    expires_on: date | None,
    opened_shelf_life_days: int | None,
    today: date,
) -> Change:
    ordered = fifo(batches)
    if not ordered:
        raise NothingToConsume
    target = ordered[0]
    if opened:
        target = next((b for b in ordered if not b.opened), ordered[0])
    after = replace(target)
    if opened and not target.opened:
        after.opened, after.opened_on = True, today
        if opened_shelf_life_days is not None:
            shortened = min(after.expires_on, today + timedelta(days=opened_shelf_life_days))
            if shortened != after.expires_on:
                after.expires_on, after.expiry_source = shortened, ExpirySource.ESTIMATED
    elif opened is False:
        after.opened, after.opened_on = False, None
    if location is not None:
        after.location = location
    if expires_on is not None:
        after.expires_on, after.expiry_source = expires_on, ExpirySource.EXPLICIT
    if (after.expires_on, after.expiry_source) != (target.expires_on, target.expiry_source):
        after.next_check_on = compute_next_check(after.expires_on, after.expiry_source)
    return Change("update", target, after)


def set_expiry(batch: Batch, expires_on: date, source: ExpirySource) -> Change:
    after = replace(
        batch,
        expires_on=expires_on,
        expiry_source=source,
        next_check_on=compute_next_check(expires_on, source),
    )
    return Change("update", batch, after)


def set_quantity(batch: Batch, quantity: Decimal) -> Change:
    """Replace the amount, expressed in the batch's own unit (the screen never converts)."""
    if not quantity.is_finite() or quantity <= 0:
        raise ValueError("Quantity must be finite and positive")
    amount = quantity.quantize(_THOUSANDTH)
    if amount <= 0:
        raise ValueError("Quantity is below the supported precision")
    return Change("update", batch, replace(batch, quantity=amount))


def mark_checked(batch: Batch, today: date) -> Change:
    return Change("check", batch, replace(batch, next_check_on=today + CHECK_AGAIN_AFTER))
