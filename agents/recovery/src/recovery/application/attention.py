"""attention.items for recovery: a depleted day calls for an easy day."""

from __future__ import annotations

from shared.attention import AttentionAction, AttentionContext, AttentionItem
from shared.ports.uow import UnitOfWork

from recovery.application.dashboard import shape


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    today = await shape(tx, ctx.dashboard, ctx.today)
    if not today or today.get("bucket") != "depleted":
        return []
    return [
        AttentionItem(
            f"recovery:depleted:{ctx.today.isoformat()}",
            "normal",
            0,
            ctx.t("attention.recovery.depleted"),
            AttentionAction("agent"),
            detail=ctx.t("attention.recovery.depleted_detail"),
        )
    ]
