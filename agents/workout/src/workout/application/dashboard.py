"""dashboard.card / dashboard.detail for workout (and the steps ring). Ported from the legacy dashboard."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from shared.dashboard import DashboardContext, empty_card, history_points
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork

ACTIVITY = "activity"
SOURCES = (("garmin", "Garmin"), ("apple_health", "Apple Health"))


def _f(value: object) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _sum(rows: Sequence[HealthLogRow], key: str) -> float | None:
    values = [v for r in rows if (v := _f(r.data.get(key))) is not None]
    return sum(values) if values else None


def _int(value: float | None) -> int | None:
    return None if value is None else round(value)


async def day_workout(tx: UnitOfWork, ctx: DashboardContext, day: date) -> dict[str, Any] | None:
    logs = tx.repo(HealthLogRepository)
    start, end = ctx.bounds(day)
    activities = [
        r
        for r in await logs.recent(ctx.user_id, types=[ACTIVITY], since=start, agent="workout")
        if r.recorded_at < end
    ]
    for source, label in SOURCES:
        rows = [r for r in activities if r.source == source]
        if rows:
            hrs = [v for r in rows if (v := _f(r.data.get("avg_hr"))) is not None]
            newest = rows[0]
            return {
                "total_calories": _int(_sum(rows, "calories")) or 0,
                "total_distance_meters": _int(_sum(rows, "distance_meters")) or 0,
                "activity_count": len(rows),
                "first_name": newest.data.get("name") or "",
                "first_type": newest.data.get("activity_type") or "",
                "avg_hr": (round(sum(hrs) / len(hrs)) if hrs else None) or 0,
                "source": label,
                "last_at": newest.recorded_at,
            }
    stats = [
        r
        for r in await logs.recent(ctx.user_id, types=["daily_stats"], since=start)
        if r.recorded_at < end
    ]
    if stats and stats[0].data.get("exerciseTime"):
        d = stats[0].data
        minutes = int(_f(d.get("exerciseTime")) or 0)
        distance = int(
            (_f(d.get("distanceWalkingRunning")) or 0) + (_f(d.get("distanceCycling")) or 0)
        )
        return {
            "total_calories": int(_f(d.get("activeEnergyBurned")) or 0),
            "total_distance_meters": distance,
            "activity_count": 1,
            "first_name": f"{minutes} min active",
            "first_type": "activity",
            "source": "Apple Health",
        }
    return None


def tile(workout: Mapping[str, Any]) -> dict[str, object]:
    km = (workout.get("total_distance_meters") or 0) / 1000
    name = workout.get("first_name") or workout.get("first_type") or "Workout"
    pills = [f"{workout['total_calories']} kcal"] if workout.get("total_calories") else []
    return {
        "agent": "workout",
        "label": "Workout",
        "metric": f"{name} · {km:.1f}km" if km > 0.1 else name,
        "tint": "neutral",
        "detail": " · ".join(pills) if pills else None,
        "progress": None,
        "workout_type": workout.get("first_type") or "",
    }


def _minutes_by_day(rows: Sequence[HealthLogRow], ctx: DashboardContext) -> dict[date, int]:
    """Aggregate before rounding, matching legacy ROUND(double precision) ties to even."""
    seconds: dict[date, float] = {}
    for r in rows:
        day = ctx.local_date(r.recorded_at)
        seconds[day] = seconds.get(day, 0.0) + (_f(r.data.get("duration_seconds")) or 0.0)
    return {day: round(total / 60.0) for day, total in seconds.items()}


async def load_history(tx: UnitOfWork, ctx: DashboardContext) -> list[int]:
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=[ACTIVITY], since=ctx.now - timedelta(days=7), agent="workout"
    )
    minutes = _minutes_by_day(rows, ctx)
    return [minutes.get(day, 0) for day in ctx.last_days(7)]


async def featured(
    tx: UnitOfWork, ctx: DashboardContext, workout: Mapping[str, Any] | None, is_today: bool
) -> dict[str, object] | None:
    loads = await load_history(tx, ctx)
    if workout:
        last = workout.get("last_at")
        return {
            "sessionName": workout.get("first_name") or workout.get("first_type") or "Workout",
            "distanceKm": round((workout.get("total_distance_meters") or 0) / 1000, 1),
            "kcal": workout.get("total_calories") or 0,
            "avgHr": workout.get("avg_hr") or 0,
            "source": workout.get("source", "Garmin"),
            "extraCount": max(0, (workout.get("activity_count") or 1) - 1),
            "loadHistory": loads,
            "workoutDate": "today" if is_today else "yesterday",
            "workoutAt": last.isoformat() if last else None,
        }
    if any(v > 0 for v in loads):
        rows = await tx.repo(HealthLogRepository).recent(
            ctx.user_id,
            types=[ACTIVITY],
            since=ctx.now - timedelta(days=7),
            agent="workout",
            limit=1,
        )
        if rows:
            r = rows[0]
            return {
                "sessionName": r.data.get("name") or r.data.get("activity_type") or "Workout",
                "distanceKm": round((_f(r.data.get("distance_meters")) or 0) / 1000, 1),
                "kcal": int(_f(r.data.get("calories")) or 0),
                "avgHr": 0,
                "source": r.source or "Garmin",
                "extraCount": 0,
                "loadHistory": loads,
                "workoutDate": "yesterday",
                "workoutAt": r.recorded_at.isoformat(),
            }
    return None


async def steps_ring(tx: UnitOfWork, ctx: DashboardContext) -> int | None:
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["daily_stats"], since=ctx.now - timedelta(hours=36)
    )
    steps = next(
        (v for r in rows if r.source == "garmin" and (v := _f(r.data.get("steps"))) and v > 0), None
    )
    return None if steps is None else min(100, round(steps / 10_000 * 100))


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    today = await day_workout(tx, ctx, ctx.today)
    is_today = bool(today and today.get("activity_count"))
    workout = today if is_today else await day_workout(tx, ctx, ctx.yesterday)
    out = empty_card()
    out["tile"] = tile(workout) if workout else None
    out["featured"] = await featured(tx, ctx, workout, is_today)
    out["rings"] = {"stepsPct": await steps_ring(tx, ctx)}
    return out


def insight(
    history: list[dict[str, object]], *, translator: Translator | None = None, locale: str = "en"
) -> str:
    active = [h for h in history if float(h["value"]) > 0]  # type: ignore[arg-type]
    if not active:
        return ""
    if translator is not None:
        return translator.t("feed.workout.insight", locale, count=len(active))
    return "1 workout this week." if len(active) == 1 else f"{len(active)} workouts this week."


async def detail(
    tx: UnitOfWork,
    ctx: DashboardContext,
    *,
    translator: Translator | None = None,
    locale: str = "en",
) -> dict[str, object]:
    logs = tx.repo(HealthLogRepository)
    rows = await logs.recent(
        ctx.user_id, types=[ACTIVITY], since=ctx.now - timedelta(days=9), agent="workout"
    )
    minutes = _minutes_by_day(rows, ctx)
    values = {day: float(value) for day, value in minutes.items()}
    history = history_points(ctx.last_days(7), values, lambda v: f"{int(v)} min" if v > 0 else "—")
    start, end = ctx.bounds(ctx.yesterday)
    day_rows = [r for r in rows if start <= r.recorded_at < end]
    metrics: dict[str, object] = {}
    duration = _int(_sum(day_rows, "duration_seconds"))
    if duration:
        metrics["duration_min"] = round(duration / 60)
        metrics["distance_km"] = round((_int(_sum(day_rows, "distance_meters")) or 0) / 1000, 2)
        metrics["kcal"] = _int(_sum(day_rows, "calories")) or 0
        if kind := day_rows[0].data.get("activity_type"):
            metrics["workout_type"] = kind
    return {
        "agent": "workout",
        "insight": insight(history, translator=translator, locale=locale),
        "metrics": metrics,
        "history": history,
    }
