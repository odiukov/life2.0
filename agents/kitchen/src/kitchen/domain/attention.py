"""What in the kitchen needs doing today: expired batches, batches spoiling today or tomorrow."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from kitchen.domain.model import Batch
from kitchen.domain.rules import fifo

MAX_EXPIRED = 5


@dataclass(frozen=True, slots=True)
class Spoilage:
    expired: tuple[Batch, ...]
    today: tuple[Batch, ...]
    tomorrow: tuple[Batch, ...]


def spoilage(active: Sequence[Batch], today: date) -> Spoilage:
    tomorrow = today + timedelta(days=1)
    ordered = fifo(active)
    return Spoilage(
        expired=tuple(b for b in ordered if b.expires_on < today),
        today=tuple(b for b in ordered if b.expires_on == today),
        tomorrow=tuple(b for b in ordered if b.expires_on == tomorrow),
    )
