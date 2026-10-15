"""dashboard.card / dashboard.detail for medication. Legacy dashboard rules."""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from shared.dashboard import DashboardContext, empty_card, history_points
from shared.ports.health_logs import HealthLogRepository
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork

from medication.application.ports import MedicationRepository

TAKEN = "medication_taken"


async def _week(tx: UnitOfWork, ctx: DashboardContext):  # type: ignore[no-untyped-def]
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=[TAKEN], since=ctx.now - timedelta(days=7), agent="medication"
    )
    return [
        r for r in rows if r.recorded_at > ctx.now - timedelta(days=7)
    ]  # the legacy query used a strict ">"


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    out = empty_card()
    active = [m.name for m in await tx.repo(MedicationRepository).active() if m.name]
    if not active:
        return out
    last: dict[str, datetime] = {}
    for r in await _week(tx, ctx):
        name = r.data.get("name")
        if isinstance(name, str) and name and (name not in last or r.recorded_at > last[name]):
            last[name] = r.recorded_at
    overdue = [n for n in active if n not in last or ctx.now - last[n] >= timedelta(days=2)]
    pills = [f"−{(ctx.now - last[n]).days}d {n}" for n in overdue[:2] if n in last]
    missed = len(overdue)
    out["tile"] = {
        "agent": "medication",
        "label": "Medication",
        "metric": " · ".join(active[:2]) if active else "On track",
        "tint": "danger" if missed > 1 else "warn" if missed == 1 else "success",
        "detail": " · ".join(pills) if pills else None,
        "progress": (len(active) - missed) / len(active),
    }
    return out


def insight(
    history: list[dict[str, object]],
    metrics: dict[str, Any],
    *,
    translator: Translator | None = None,
    locale: str = "en",
) -> str:
    missed, adherence = metrics.get("missed_names") or [], metrics.get("adherence_7d", 1.0)
    if not missed and adherence >= 0.95:
        if translator is not None:
            return translator.t("feed.medication.insight.full", locale)
        return "Full adherence this week. Keep it up."
    if missed:
        names = ", ".join(missed[:3]) + (" and more" if len(missed) > 3 else "")
        n = sum(1 for h in history if h["value"] == 0)
        if translator is not None:
            more = translator.t("feed.medication.insight.more", locale) if len(missed) > 3 else ""
            return translator.t(
                "feed.medication.insight.missed",
                locale,
                days=n,
                names=", ".join(missed[:3]),
                more=more,
            )
        return f"Missed {n} day(s) this week: {names}."
    if translator is not None:
        return translator.t("feed.medication.insight.rate", locale, percent=int(adherence * 100))
    return f"{int(adherence * 100)}% adherence this week."


async def detail(
    tx: UnitOfWork,
    ctx: DashboardContext,
    *,
    translator: Translator | None = None,
    locale: str = "en",
) -> dict[str, object]:
    logs = tx.repo(HealthLogRepository)
    month = await logs.recent(
        ctx.user_id, types=[TAKEN], since=ctx.now - timedelta(days=32), agent="medication"
    )
    taken_days = {ctx.local_date(r.recorded_at) for r in month}
    history = history_points(
        ctx.last_days(30), dict.fromkeys(taken_days, 1.0), lambda v: "✅" if v else "⬜"
    )
    meds = await tx.repo(MedicationRepository).active()
    week = await _week(tx, ctx)
    week_days = {ctx.local_date(r.recorded_at) for r in week}
    adherence = (
        len([d for d in (ctx.today - timedelta(days=i) for i in range(7)) if d in week_days]) / 7.0
    )
    recent_names = {
        r.data.get("name")
        for r in week
        if ctx.local_date(r.recorded_at) >= ctx.today - timedelta(days=2)
    }
    metrics = {
        "adherence_7d": round(adherence, 2),
        "active_count": len(meds),
        "missed_names": [m.name for m in meds if m.name not in recent_names],
    }
    return {
        "agent": "medication",
        "insight": insight(history, metrics, translator=translator, locale=locale),
        "metrics": metrics,
        "history": history,
    }
