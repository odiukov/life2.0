"""attention.items for workout: plan a workout after a quiet stretch."""

from __future__ import annotations

from datetime import timedelta

from shared.attention import AttentionAction, AttentionContext, AttentionItem
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork

from workout.domain.attention import WINDOW_DAYS, quiet_days


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    since, _ = ctx.bounds(ctx.today - timedelta(days=WINDOW_DAYS))
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["activity"], since=since, agent="workout"
    )
    days = [r.recorded_at.astimezone(ctx.zone).date() for r in rows]
    gap = quiet_days(days, ctx.today)
    if gap is None:
        return []
    return [
        AttentionItem(
            f"workout:plan:{max(days).isoformat()}",
            "high",
            -gap,
            ctx.t("attention.workout.plan"),
            AttentionAction("task", ctx.t("attention.workout.prompt")),
            detail=ctx.t("attention.workout.plan_detail", count=gap),
        )
    ]
