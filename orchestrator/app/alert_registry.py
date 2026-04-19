from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Awaitable, Callable, Sequence

from .alerts import Alert


FetchLast = Callable[[str], Awaitable[datetime | None]]
UpsertLast = Callable[[str, datetime], Awaitable[None]]


@dataclass
class AlertRegistry:
    fetch_last: FetchLast
    upsert_last: UpsertLast

    async def filter_fresh(
        self, alerts: Sequence[Alert], now: datetime | None = None
    ) -> list[Alert]:
        now = now or datetime.now(timezone.utc)
        kept: list[Alert] = []
        for a in alerts:
            last = await self.fetch_last(a.rule_id)
            if last is None or (now - last) >= timedelta(hours=a.throttle_hours):
                kept.append(a)
        return kept

    async def mark_emitted(
        self, alerts: Sequence[Alert], now: datetime | None = None
    ) -> None:
        now = now or datetime.now(timezone.utc)
        for a in alerts:
            await self.upsert_last(a.rule_id, now)
