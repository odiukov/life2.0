"""feed.events for body: scale measurements of the user's local day (body has no detail insight)."""

from __future__ import annotations

from datetime import timedelta

from shared.feed import FeedContext, FeedItem, day_rows, prefer_sources, row_id
from shared.ports.health_logs import HealthLogRow
from shared.ports.uow import UnitOfWork

from body.domain.measurement import BodyMeasurement

SAME_WEIGH_IN = timedelta(minutes=10)


def _same(a: HealthLogRow, b: HealthLogRow) -> bool:
    return abs(a.recorded_at - b.recorded_at) <= SAME_WEIGH_IN


def _text(ctx: FeedContext, m: BodyMeasurement) -> str | None:
    if m.weight_kg is None:
        return None
    text = ctx.t("feed.body.weight", kg=ctx.tr.number(m.weight_kg, ctx.locale, digits=1))
    if m.body_fat_pct is not None:
        text = ctx.t(
            "feed.body.fat", text=text, pct=ctx.tr.number(m.body_fat_pct, ctx.locale, digits=1)
        )
    return text


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    rows = [
        r
        for r in await day_rows(tx, ctx, types=["body_composition"], agent="body")
        if BodyMeasurement.from_row(r).weight_kg is not None
    ]
    items = []
    for row in prefer_sources(rows, ("vihealth",), same=_same):
        text = _text(ctx, BodyMeasurement.from_row(row))
        if text:
            items.append(FeedItem(row_id("body", row), row.recorded_at, "event", text))
    return items
