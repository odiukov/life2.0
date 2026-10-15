"""feed.events for mood: the entries of the user's local day, plus today's insight."""

from __future__ import annotations

from shared.feed import FeedContext, FeedItem, day_rows, insight_items, row_id
from shared.ports.uow import UnitOfWork

from mood.application.dashboard import detail
from mood.domain.entry import MoodEntry


def _text(ctx: FeedContext, e: MoodEntry) -> str:
    if e.mood_score is None:
        return ctx.t("feed.mood.note")
    text = ctx.t("feed.mood.entry", score=e.mood_score)
    if e.energy is not None:
        text = ctx.t("feed.mood.energy", text=text, value=e.energy)
    return text


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    rows = await day_rows(tx, ctx, types=["mood"], agent="mood")
    items = [
        FeedItem(row_id("mood", r), r.recorded_at, "event", _text(ctx, MoodEntry.from_row(r)))
        for r in rows
    ]
    if ctx.is_today:
        items += insight_items(
            "mood", ctx, await detail(tx, ctx.dashboard, translator=ctx.tr, locale=ctx.locale)
        )
    return items
