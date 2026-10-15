"""feed.events for workout: sessions of the user's local day, plus today's insight."""

from __future__ import annotations

from datetime import timedelta

from shared.feed import (
    FeedContext,
    FeedItem,
    day_rows,
    duration_text,
    insight_items,
    prefer_sources,
    row_id,
)
from shared.ports.health_logs import HealthLogRow
from shared.ports.uow import UnitOfWork

from workout.application.dashboard import detail
from workout.domain.workout import Workout

SOURCES = ("garmin", "SourceProxy")
SAME_SESSION = timedelta(minutes=10)


def _same(a: HealthLogRow, b: HealthLogRow) -> bool:
    return abs(a.recorded_at - b.recorded_at) <= SAME_SESSION


def _text(ctx: FeedContext, w: Workout) -> str:
    name = w.name.strip() or ctx.t("feed.workout.unnamed")
    text = (
        ctx.t("feed.workout.session", name=name, duration=duration_text(ctx, w.duration_s))
        if w.duration_s
        else ctx.t("feed.workout.short", name=name)
    )
    if w.distance_m:
        text = ctx.t(
            "feed.workout.distance",
            text=text,
            km=ctx.tr.number(w.distance_m / 1000, ctx.locale, digits=1),
        )
    return text


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    rows = prefer_sources(
        await day_rows(tx, ctx, types=["activity"], agent="workout"), SOURCES, same=_same
    )
    items = [
        FeedItem(row_id("workout", r), r.recorded_at, "event", _text(ctx, Workout.from_row(r)))
        for r in rows
    ]
    if ctx.is_today:
        items += insight_items("workout", ctx, await detail(tx, ctx.dashboard))
    return items
