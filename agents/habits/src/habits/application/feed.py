"""feed.events for habits: check-ins of the user's local day, plus today's insight."""

from __future__ import annotations

from shared.feed import FeedContext, FeedItem, day_rows, insight_items, row_id
from shared.ports.health_logs import HealthLogRow
from shared.ports.uow import UnitOfWork

from habits.application.dashboard import detail


def _text(ctx: FeedContext, row: HealthLogRow) -> str:
    name = str(row.data.get("name") or "").strip() or "—"
    value = row.data.get("value")
    if isinstance(value, int | float) and not isinstance(value, bool):
        return ctx.t(
            "feed.habits.value", name=name, value=f"{value:g}", unit=str(row.data.get("unit") or "")
        ).rstrip()
    return ctx.t("feed.habits.check", name=name)


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    rows = await day_rows(tx, ctx, types=["habit"], agent="habits")
    items = [FeedItem(row_id("habits", r), r.recorded_at, "event", _text(ctx, r)) for r in rows]
    if ctx.is_today:
        items += insight_items(
            "habits", ctx, await detail(tx, ctx.dashboard, translator=ctx.tr, locale=ctx.locale)
        )
    return items
