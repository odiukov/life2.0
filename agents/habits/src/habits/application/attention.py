"""attention.items for habits: what is still open this evening."""

from __future__ import annotations

from shared.attention import AttentionAction, AttentionContext, AttentionItem
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork

from habits.application.ports import HabitRepository
from habits.domain.attention import HABITS_EVENING_HOUR, due_unchecked
from habits.domain.habit import HabitCheck


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    if ctx.now_local.hour < HABITS_EVENING_HOUR:
        return []
    habits = await tx.repo(HabitRepository).active()
    if not habits:
        return []
    start, end = ctx.bounds(ctx.today)
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["habit"], since=start, until=end, agent="habits"
    )
    checked = {c.habit_id for c in map(HabitCheck.from_row, rows) if c.completed}
    open_ = due_unchecked(habits, checked, ctx.today)
    if not open_:
        return []
    return [
        AttentionItem(
            f"habits:due:{ctx.today.isoformat()}",
            "normal",
            0,
            ctx.t("attention.habits.due", count=len(open_)),
            AttentionAction("agent"),
            detail=", ".join(h.name for h in open_),
        )
    ]
