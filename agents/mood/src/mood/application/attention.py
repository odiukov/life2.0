"""attention.items for mood: no check-in for a few days."""

from __future__ import annotations

from shared.attention import AttentionAction, AttentionContext, AttentionItem, days_since, stale
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork

from mood.domain.attention import MOOD_DAYS


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["mood"], agent="mood", limit=1
    )
    if not rows:
        return []
    gap = days_since(ctx, rows[0].recorded_at)
    if not stale(gap, MOOD_DAYS):
        return []
    return [
        AttentionItem(
            f"mood:checkin:{rows[0].recorded_at.astimezone(ctx.zone).date().isoformat()}",
            "normal",
            -gap,
            ctx.t("attention.mood.checkin"),
            AttentionAction("task", ctx.t("attention.mood.prompt")),
            detail=ctx.t("attention.mood.checkin_detail", count=gap),
        )
    ]
