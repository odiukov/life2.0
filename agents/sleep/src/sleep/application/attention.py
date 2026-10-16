"""attention.items for sleep: two short nights in a row."""

from __future__ import annotations

from datetime import date, datetime, timedelta

from shared.attention import AttentionAction, AttentionContext, AttentionItem
from shared.feed import prefer_sources
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWork

from sleep.application.feed import SAME_NIGHT, SOURCES
from sleep.domain.attention import short_streak
from sleep.domain.session import SleepSession


def _same(a: HealthLogRow, b: HealthLogRow) -> bool:
    return abs(a.recorded_at - b.recorded_at) <= SAME_NIGHT


def _wake(session: SleepSession, recorded_at: datetime, seconds: int) -> datetime:
    """When the night ended: rows are anchored at bedtime (Garmin and chat store the start)."""
    return session.end or recorded_at + timedelta(seconds=seconds)


async def collect(tx: UnitOfWork, ctx: AttentionContext) -> list[AttentionItem]:
    # recorded_at is bedtime, so yesterday's night may have started the evening before.
    since, _ = ctx.bounds(ctx.today - timedelta(days=2))
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["sleep_session"], since=since, agent="sleep"
    )
    nights: dict[date, int] = {}
    for row in prefer_sources(rows, SOURCES, same=_same):
        session = SleepSession.from_row(row)
        seconds = session.duration_s
        if seconds:
            day = _wake(session, row.recorded_at, seconds).astimezone(ctx.zone).date()
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
