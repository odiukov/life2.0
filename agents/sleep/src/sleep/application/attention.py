"""attention.items for sleep: two short nights in a row."""

from __future__ import annotations

from datetime import date, timedelta

from shared.attention import AttentionAction, AttentionContext, AttentionItem
from shared.feed import prefer_sources
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWork

from sleep.application.feed import SAME_NIGHT, SOURCES
from sleep.domain.attention import short_streak
from sleep.domain.session import SleepSession


def _same(a: HealthLogRow, b: HealthLogRow) -> bool:
    return abs(a.recorded_at - b.recorded_at) <= SAME_NIGHT


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    since, _ = ctx.bounds(ctx.today - timedelta(days=1))
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["sleep_session"], since=since, agent="sleep"
    )
    nights: dict[date, int] = {}
    for row in prefer_sources(rows, SOURCES, same=_same):
        seconds = SleepSession.from_row(row).duration_s
        if seconds:
            day = row.recorded_at.astimezone(ctx.zone).date()
            nights[day] = max(nights.get(day, 0), seconds)
    if not short_streak(nights, ctx.today):
        return []
    return [
        AttentionItem(
            f"sleep:short:{ctx.today.isoformat()}",
            "normal",
            0,
            ctx.t("attention.sleep.short"),
            AttentionAction("agent"),
            detail=ctx.t("attention.sleep.short_detail"),
        )
    ]
