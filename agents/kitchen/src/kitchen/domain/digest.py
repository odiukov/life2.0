"""Daily spoilage-check digest."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import date, timedelta

from kitchen.domain.model import Batch
from kitchen.domain.rules import fifo


@dataclass(frozen=True, slots=True)
class DigestView:
    expired: tuple[Batch, ...]
    expiring: tuple[Batch, ...]
    to_check: tuple[Batch, ...]
    hidden: int

    @property
    def is_empty(self) -> bool:
        return not (self.expired or self.expiring or self.to_check)

    def items(self) -> list[Batch]:
        return [*self.expired, *self.expiring, *self.to_check]


def build_digest(active: Sequence[Batch], today: date, limit: int = 15) -> DigestView:
    if limit < 0:
        raise ValueError("Digest limit must not be negative")
    tomorrow = today + timedelta(days=1)
    expired, expiring, to_check = [], [], []
    for batch in fifo(active):
        if batch.expires_on < today:
            expired.append(batch)
        elif batch.expires_on <= tomorrow:
            expiring.append(batch)
        elif batch.next_check_on <= today:
            to_check.append(batch)
    total = len(expired) + len(expiring) + len(to_check)
    budget = limit
    groups = []
    for group in (expired, expiring, to_check):
        groups.append(tuple(group[:budget]))
        budget = max(0, budget - len(group))
    return DigestView(groups[0], groups[1], groups[2], hidden=max(0, total - limit))
