"""dashboard.detail for finance. Legacy rules; months and days in the user's zone."""

from __future__ import annotations

from collections import Counter
from datetime import date, timedelta
from decimal import Decimal
from typing import cast

from shared.dashboard import DashboardContext, history_points, pg_round
from shared.ports.uow import UnitOfWork

from finance.application.ports import TransactionRepository
from finance.domain.figures import month_bounds, runway, spending_by_category


def insight(history: list[dict[str, object]], top: str) -> str:
    values = [cast(float, h["value"]) for h in history]
    if len(values) < 4:
        return ""
    mid = len(values) // 2
    first = sum(values[:mid]) / mid if mid else 0
    last = sum(values[mid:]) / len(values[mid:]) if values[mid:] else 0
    if first == 0:
        return ""
    pct = (last - first) / first * 100
    suffix = f" Top: {top}." if top else ""
    if pct > 15:
        return f"Spending up {pct:.0f}% vs earlier this week.{suffix}"
    if pct < -15:
        return f"Spending down {abs(pct):.0f}% vs earlier this week.{suffix}"
    return f"Top category: {top}." if top else ""


async def detail(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    repo = tx.repo(TransactionRepository)
    everything = await repo.all(ctx.user_id)
    counts = Counter(t.currency for t in everything)
    primary = counts.most_common(1)[0][0] if counts else None
    since = ctx.now - timedelta(days=9)
    per_day: dict[date, Decimal] = {}
    for t in everything:
        if t.direction == "OUT" and t.currency == primary and t.ts >= since:
            day = ctx.local_date(t.ts)
            per_day[day] = per_day.get(day, Decimal(0)) + t.amount
    values = {day: pg_round(total, 2) for day, total in per_day.items()}
    history = history_points(ctx.last_days(7), values, lambda v: f"${v:.0f}" if v > 0 else "—")
    month = ctx.today.strftime("%Y-%m")
    start, end = month_bounds(month, ctx.zone)
    categories = spending_by_category([t for t in everything if start <= t.ts < end])
    top = categories[0][0] if categories else ""
    window = [t for t in everything if t.ts >= ctx.now - timedelta(days=30)]
    first = next(iter(runway(everything, window, 30).values()), None)
    metrics: dict[str, object] = {
        "spent_week": round(sum(cast(float, h["value"]) for h in history), 2)
    }
    if top:
        metrics["top_category"] = top
    if first is not None and first.days:
        metrics["runway_days"] = first.days
    return {
        "agent": "finance",
        "insight": insight(history, top),
        "metrics": metrics,
        "history": history,
    }
