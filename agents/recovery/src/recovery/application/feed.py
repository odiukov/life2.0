"""feed.events for recovery: no stored events of its own; today's readiness insight only."""

from __future__ import annotations

from shared.feed import FeedContext, FeedItem, insight_items
from shared.ports.uow import UnitOfWork

from recovery.application.dashboard import detail


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    return (
        insight_items(
            "recovery", ctx, await detail(tx, ctx.dashboard, translator=ctx.tr, locale=ctx.locale)
        )
        if ctx.is_today
        else []
    )
