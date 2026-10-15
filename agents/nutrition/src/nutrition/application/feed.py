"""feed.events for nutrition: the meals of the user's local day, plus today's insight."""

from __future__ import annotations

from shared.feed import FeedContext, FeedItem, insight_items
from shared.ports.uow import UnitOfWork

from nutrition.application.dashboard import detail
from nutrition.application.ports import MealRepository
from nutrition.domain.meal import Meal


def _text(ctx: FeedContext, meal: Meal) -> str:
    kind = (
        ctx.t(f"feed.nutrition.type.{meal.meal_type.value}")
        if meal.meal_type
        else ctx.t("feed.nutrition.type.other")
    )
    return ctx.t(
        "feed.nutrition.meal",
        meal=kind,
        kcal=round(meal.totals.kcal),
        protein=round(meal.totals.protein_g),
    )


async def collect(tx: UnitOfWork, ctx: FeedContext) -> list[FeedItem]:
    start, end = ctx.bounds()
    meals = await tx.repo(MealRepository).between(ctx.user_id, start, end)
    items = [
        FeedItem(
            f"nutrition:meal:{m.source}:{m.recorded_at.isoformat()}",
            m.recorded_at,
            "event",
            _text(ctx, m),
        )
        for m in meals
    ]
    if ctx.is_today:
        items += insight_items(
            "nutrition", ctx, await detail(tx, ctx.dashboard, translator=ctx.tr, locale=ctx.locale)
        )
    return items
