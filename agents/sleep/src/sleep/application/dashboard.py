"""dashboard.card / dashboard.detail for sleep. Ported from the legacy orchestrator dashboard."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
from decimal import Decimal
from typing import Any

from shared.dashboard import DashboardContext, empty_card, fmt_duration, history_points, pg_round
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWork

SESSION, HRV_STATUS = "sleep_session", "hrv_status"
LOOKBACK = timedelta(hours=36)
SOURCES = (("garmin", "Garmin"), ("SourceProxy", "Apple Health"))


def _f(value: object) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _pg_int(value: object) -> int | None:
    """`(x)::float::int` in Postgres: ties to even, like Python's round()."""
    number = _f(value)
    return None if number is None else round(number)


async def last_night(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, Any] | None:
    logs = tx.repo(HealthLogRepository)
    start, end = ctx.bounds(ctx.yesterday)
    since = start - LOOKBACK
    sessions = await logs.recent(ctx.user_id, types=[SESSION], since=since, agent="sleep")
    for source, label in SOURCES:  # noqa: B007 - selected label is returned after the loop
        row = next((r for r in sessions if r.source == source), None)
        if row is not None:
            break
    else:
        return None
    statuses = [
        r
        for r in await logs.recent(ctx.user_id, types=[HRV_STATUS], since=since, agent="sleep")
        if r.recorded_at < end
    ]
    rmssd = _f(statuses[0].data.get("hrv_rmssd")) if statuses else None
    weekly = _f(row.data.get("hrv_weekly_avg"))
    hrv = int(rmssd) if rmssd else (int(weekly) if weekly else None)
    return {
        "duration_seconds": _pg_int(row.data.get("duration_seconds")) or 0,
        "deep_sleep_seconds": _pg_int(row.data.get("deep_sleep_seconds")) or 0,
        "hrv": hrv,
        "avg_hr": _pg_int(row.data.get("avg_hr")),
        "score": _pg_int(row.data.get("score")),
        "source": label,
    }


def tile(sleep: Mapping[str, Any]) -> dict[str, object]:
    secs = sleep["duration_seconds"]
    hours = secs / 3600
    pills = []
    if sleep.get("deep_sleep_seconds") is not None:
        pills.append(f"Deep {fmt_duration(sleep['deep_sleep_seconds'])}")
    if sleep.get("hrv") is not None:
        pills.append(f"HRV {sleep['hrv']}")
    if sleep.get("score") is not None:
        pills.append(f"Score {sleep['score']}")
    return {
        "agent": "sleep",
        "label": "Sleep",
        "metric": fmt_duration(secs),
        "tint": "success" if hours >= 7 else "warn",
        "detail": " · ".join(pills) if pills else None,
        "progress": min(hours / 8.0, 1.0),
    }


def featured(sleep: Mapping[str, Any]) -> dict[str, object]:
    secs = sleep.get("duration_seconds") or 0
    deep = sleep.get("deep_sleep_seconds") or 0
    return {
        "durationLabel": fmt_duration(secs) if secs else "—",
        "durationPct": min(100, round(secs / (8 * 3600) * 100)) if secs else 0,
        "deepLabel": fmt_duration(deep) if deep else "—",
        "deepPct": min(100, round(deep / secs * 100)) if secs > 0 else 0,
        "hrv": sleep.get("hrv") or 0,
        "avgHr": sleep.get("avg_hr") or 0,
        "hrvDelta": "—",
        "source": sleep.get("source", "Garmin"),
        "insight": None,
    }


async def hrv_ring(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    logs = tx.repo(HealthLogRepository)
    since = ctx.now - timedelta(days=7)
    statuses = [
        r
        for r in await logs.recent(ctx.user_id, types=[HRV_STATUS], since=since, agent="sleep")
        if _f(r.data.get("hrv_rmssd")) is not None
    ]
    ms: int | None = None
    low = high = None
    if statuses:
        values = [_f(r.data["hrv_rmssd"]) or 0.0 for r in statuses]
        average = sum(values) / len(values)
        ms = round(average) if average else None
        low, high = (
            _f(statuses[0].data.get("baseline_low")),
            _f(statuses[0].data.get("baseline_high")),
        )
    if ms is None:
        weekly = [
            v
            for r in await logs.recent(ctx.user_id, types=[SESSION], since=since, agent="sleep")
            if (v := _f(r.data.get("hrv_weekly_avg"))) is not None
        ]
        if weekly and (average := sum(weekly) / len(weekly)):
            ms = round(average)
    if ms is None:
        pct = None
    elif low and high and high > low:
        pct = min(100, max(0, round((ms - low) / (high - low) * 100)))
    else:
        pct = min(100, round(ms / 80 * 100))
    return {"hrvPct": pct, "hrvMs": ms}


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    sleep = await last_night(tx, ctx)
    out = empty_card()
    if sleep is not None:
        out["tile"] = tile(sleep) if sleep.get("duration_seconds") is not None else None
        out["featured"] = featured(sleep)
    out["rings"] = await hrv_ring(tx, ctx)
    return out


def _hours_label(value: float) -> str:
    if value == 0.0:
        return "—"
    hours = int(value)
    minutes = round((value - hours) * 60)
    return f"{hours}h {minutes}m" if minutes else f"{hours}h"


def insight(history: list[dict[str, object]]) -> str:
    values = [float(h["value"]) for h in history if float(h["value"]) > 0]  # type: ignore[arg-type]
    if len(values) < 3:
        return ""
    average = sum(values[:-1]) / len(values[:-1])
    last = values[-1]
    above = sum(1 for v in values[-3:] if v > average)
    if above >= 2:
        return f"Above weekly average {above} of last 3 nights."
    if last < average - 0.5:
        return f"Below weekly average by {average - last:.1f}h last night."
    return ""


async def detail(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    logs = tx.repo(HealthLogRepository)
    rows = await logs.recent(
        ctx.user_id, types=[SESSION], since=ctx.now - timedelta(days=9), agent="sleep"
    )
    longest: dict[object, int] = {}
    for r in rows:
        if (secs := _pg_int(r.data.get("duration_seconds"))) is not None:
            day = ctx.local_date(r.recorded_at)
            longest[day] = max(longest.get(day, secs), secs)
    values = {day: pg_round(Decimal(secs) / Decimal(3600), 2) for day, secs in longest.items()}
    history = history_points(ctx.last_days(7), values, _hours_label)  # type: ignore[arg-type]
    start, _ = ctx.bounds(ctx.yesterday)
    latest: HealthLogRow | None = next(
        iter(
            await logs.recent(
                ctx.user_id, types=[SESSION], since=start - LOOKBACK, agent="sleep", limit=1
            )
        ),
        None,
    )
    metrics: dict[str, object] = {}
    if latest is not None:
        duration = _pg_int(latest.data.get("duration_seconds")) or 0
        deep = _pg_int(latest.data.get("deep_sleep_seconds")) or 0
        hrv = _f(latest.data.get("hrv_weekly_avg"))
        metrics["deep_hours"] = round(deep / 3600, 2)
        metrics["hrv"] = int(hrv) if hrv else None
        metrics["efficiency_pct"] = round(deep / duration * 100) if duration else None
    return {
        "agent": "sleep",
        "insight": insight(history),
        "metrics": {k: v for k, v in metrics.items() if v is not None},
        "history": history,
    }
