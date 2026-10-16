"""attention.items for body: a regular weigher has not weighed in for a week."""

from __future__ import annotations

from shared.attention import AttentionAction, AttentionContext, AttentionItem, days_since, stale
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork

from body.domain.attention import WEIGH_DAYS
from body.domain.measurement import BodyMeasurement


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["body_composition"], agent="body", limit=20
    )
    weighed = [r for r in rows if BodyMeasurement.from_row(r).weight_kg is not None]
    if not weighed:
        return []
    last = weighed[0]
    gap = days_since(ctx, last.recorded_at)
    if not stale(gap, WEIGH_DAYS):
        return []
    return [
        AttentionItem(
            f"body:weigh:{last.recorded_at.astimezone(ctx.zone).date().isoformat()}",
            "normal",
            -gap,
            ctx.t("attention.body.weigh"),
            AttentionAction("task", ctx.t("attention.body.prompt")),
            detail=ctx.t("attention.body.weigh_detail", count=gap),
        )
    ]
