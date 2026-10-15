"""feed.events for medication: intakes of the user's local day, plus today's insight."""

from __future__ import annotations

from shared.feed import FeedContext, FeedItem, day_rows, insight_items, row_id
from shared.ports.health_logs import HealthLogRow
from shared.ports.uow import UnitOfWork

from medication.application.dashboard import detail


def _text(ctx: FeedContext, row: HealthLogRow) -> str:
    name = str(row.data.get("name") or "").strip() or "—"
    dose = row.data.get("dose_at_time")
    return (
        ctx.t("feed.medication.dose", name=name, dose=dose)
        if isinstance(dose, str) and dose.strip()
        else ctx.t("feed.medication.taken", name=name)
    )


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    rows = await day_rows(tx, ctx, types=["medication_taken"], agent="medication")
    items = [FeedItem(row_id("medication", r), r.recorded_at, "event", _text(ctx, r)) for r in rows]
    if ctx.is_today:
        items += insight_items(
            "medication", ctx, await detail(tx, ctx.dashboard, translator=ctx.tr, locale=ctx.locale)
        )
    return items
