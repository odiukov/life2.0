"""attention.items for nutrition: the body profile the calorie goal needs, and no meals by 14:00."""

from __future__ import annotations

from shared.attention import AttentionAction, AttentionContext, AttentionItem
from shared.ports.health_logs import HealthLogRepository
from shared.ports.profile import BodyProfileRepository
from shared.ports.uow import UnitOfWork

from nutrition.application.dashboard import calorie_goal
from nutrition.application.ports import MealRepository

MEALS_HOUR = 14


async def _has_goal(tx: UnitOfWork, ctx: AttentionContext) -> bool:
    profile = await tx.repo(BodyProfileRepository).get(ctx.user_id)
    try:
        weight = profile.get("weight_kg")
        if weight is None:
            latest = await tx.repo(HealthLogRepository).recent(
                ctx.user_id, types=["body_composition"], limit=1
            )
            weight = latest[0].data.get("weight_kg") if latest else None
        return calorie_goal(profile, weight) is not None
    except (TypeError, ValueError):
        return False


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    items = []
    if not await _has_goal(tx, ctx):
        items.append(
            AttentionItem(
                "nutrition:profile",
                "high",
                0,
                ctx.t("attention.nutrition.profile"),
                AttentionAction("profile"),
                detail=ctx.t("attention.nutrition.profile_detail"),
            )
        )
    if ctx.now_local.hour >= MEALS_HOUR:
        start, end = ctx.bounds(ctx.today)
        if not await tx.repo(MealRepository).between(ctx.user_id, start, end):
            items.append(
                AttentionItem(
                    f"nutrition:meals:{ctx.today.isoformat()}",
                    "normal",
                    0,
                    ctx.t("attention.nutrition.meals"),
                    AttentionAction("task", ctx.t("attention.nutrition.prompt")),
                    detail=ctx.t("attention.nutrition.meals_detail"),
                )
            )
    return items
