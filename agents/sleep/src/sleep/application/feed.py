"""feed.events for sleep: the nights (and naps) of the user's local day, plus today's insight."""

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

from sleep.application.dashboard import detail
from sleep.domain.session import SleepSession

SOURCES = ("garmin", "SourceProxy")
SAME_NIGHT = timedelta(hours=3)


def _same(a: HealthLogRow, b: HealthLogRow) -> bool:
    return abs(a.recorded_at - b.recorded_at) <= SAME_NIGHT


def _text(ctx: FeedContext, session: SleepSession) -> str | None:
    if not session.duration_s:
        return None
    text = ctx.t("feed.sleep.night", duration=duration_text(ctx, session.duration_s))
    if session.deep_s:
        text = ctx.t("feed.sleep.deep", text=text, duration=duration_text(ctx, session.deep_s))
    return text


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    rows = prefer_sources(
        await day_rows(tx, ctx, types=["sleep_session"], agent="sleep"), SOURCES, same=_same
    )
    items = []
    for row in rows:
        text = _text(ctx, SleepSession.from_row(row))
        if text:
            items.append(FeedItem(row_id("sleep", row), row.recorded_at, "event", text))
    if ctx.is_today:
        items += insight_items("sleep", ctx, await detail(tx, ctx.dashboard))
    return items
