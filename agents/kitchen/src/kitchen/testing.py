"""Test helpers and in-memory repositories with the same contract as the SQL ones."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from typing import Any
from uuid import UUID

from kitchen.domain.model import Batch, Category, ExpirySource, Location, Source, Status, Unit

NOW = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
TODAY = date(2026, 10, 13)


def make_batch(**overrides: Any) -> Batch:
    """Brownie-compatible builder: integer ids/authors become UUID(int=n); ids keep FIFO order."""
    raw_id = overrides.get("id")
    if isinstance(raw_id, int):
        overrides["id"] = UUID(int=raw_id)
        overrides.setdefault("added_at", NOW + timedelta(microseconds=raw_id))
    if isinstance(overrides.get("added_by"), int):
        overrides["added_by"] = UUID(int=overrides["added_by"])
    base = Batch(
        id=None,
        name="молоко",
        display_name="молоко 3.2%",
        category=Category.DAIRY,
        quantity=Decimal("1000"),
        unit=Unit.ML,
        location=Location.FRIDGE,
        status=Status.ACTIVE,
        opened=False,
        opened_on=None,
        added_at=NOW,
        added_by=None,
        expires_on=date(2026, 10, 20),
        expiry_source=ExpirySource.ESTIMATED,
        next_check_on=date(2026, 10, 19),
        source=Source.TEXT,
    )
    return replace(base, **overrides)
