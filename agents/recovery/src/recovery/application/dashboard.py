"""dashboard.card / dashboard.detail for recovery (and the readiness ring). Legacy dashboard rules."""

from __future__ import annotations

from datetime import date, timedelta
from typing import Any

from shared.dashboard import DashboardContext, empty_card, history_points
from shared.domain.recovery import baseline_mean, compute_bucket, compute_deltas, format_top3
from shared.ports.health_logs import HealthLogRepository
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork

READY_PCT = {"recovered": 85, "neutral": 55, "depleted": 20}
TINT = {"recovered": "success", "neutral": "warn", "depleted": "danger"}
RECOVERY_BUCKET_PROGRESS = {"recovered": 0.85, "neutral": 0.55, "depleted": 0.20}


def _f(value: object) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _int(value: object) -> int | None:
    number = _f(value)
    return None if number is None else round(number)


def _empty() -> dict[str, Any]:
    return dict.fromkeys(
        (
            "hrv",
            "rhr",
            "stress",
            "bb_min",
            "bb_max",
            "sleep_score",
            "hrv_sdnn",
            "sleep_duration_h",
            "sleep_efficiency_pct",
        )
    )


async def daily_metrics(
    tx: UnitOfWork, ctx: DashboardContext, days: int
) -> dict[date, dict[str, Any]]:
    """Port of shared.db.fetch_recovery_metrics: per local day, HRV Status wins over the sleep-DTO HRV."""
    logs = tx.repo(HealthLogRepository)
    since = ctx.now - timedelta(days=days)
    out: dict[date, dict[str, Any]] = {}
    for r in reversed(
        await logs.recent(ctx.user_id, types=["sleep_session"], since=since, agent="sleep")
    ):
        day = out.setdefault(ctx.local_date(r.recorded_at), _empty())
        if (hrv := _f(r.data.get("hrv_weekly_avg"))) is not None:
            day["hrv"] = day["hrv_sdnn"] = hrv
        if (score := _int(r.data.get("score"))) is not None:
            day["sleep_score"] = score
        duration, awake = _f(r.data.get("duration_seconds")), _f(r.data.get("awake_seconds"))
        if duration:
            day["sleep_duration_h"] = round(duration / 3600, 2)
            if awake is not None:
                day["sleep_efficiency_pct"] = round(
                    max(0.0, (duration - awake) / duration * 100), 1
                )
    # Garmin and HealthKit store the same daily shape under different source owners.
    daily = [
        row
        for owner in ("sleep", "system")
        for row in await logs.recent(ctx.user_id, types=["daily_stats"], since=since, agent=owner)
    ]
    for r in sorted(daily, key=lambda row: row.recorded_at):
        day = out.setdefault(ctx.local_date(r.recorded_at), _empty())
        for key, field in (
            ("rhr", "resting_hr"),
            ("stress", "stress_avg"),
            ("bb_min", "body_battery_min"),
            ("bb_max", "body_battery_max"),
        ):
            if (value := _int(r.data.get(field))) is not None:
                day[key] = value
    for r in reversed(
        await logs.recent(ctx.user_id, types=["hrv_status"], since=since, agent="sleep")
    ):
        if (rmssd := _f(r.data.get("hrv_rmssd"))) is not None:
            day = out.setdefault(ctx.local_date(r.recorded_at), _empty())
            day["hrv"] = day["hrv_sdnn"] = rmssd
    return out


async def shape(tx: UnitOfWork, ctx: DashboardContext, target: date) -> dict[str, Any] | None:
    """Port of recovery_context.fetch_recovery_shape."""
    metrics = await daily_metrics(tx, ctx, days=8)
    if not metrics:
        return None
    key = target if target in metrics else max(metrics)
    baseline = baseline_mean([metrics[k] for k in sorted(metrics, reverse=True) if k != key][:7])
    bucket = compute_bucket(metrics[key], baseline)
    if bucket == "unknown":
        return None
    return {"bucket": bucket, "top3": format_top3(compute_deltas(metrics[key], baseline))}


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    recovery = await shape(tx, ctx, ctx.yesterday)
    out = empty_card()
    bucket = (recovery or {}).get("bucket")
    if bucket:
        pills = [
            f"{s['label']} {s['dir']}{s['delta']}" if s.get("delta") else f"{s['label']} {s['dir']}"
            for s in (recovery or {}).get("top3", [])[:3]
            if s.get("label") and s.get("dir")
        ]
        out["tile"] = {
            "agent": "recovery",
            "label": "Recovery",
            "metric": str(bucket).capitalize(),
            "tint": TINT.get(str(bucket), "neutral"),
            "detail": " · ".join(pills) if pills else None,
            "progress": RECOVERY_BUCKET_PROGRESS.get(str(bucket)),
        }
    out["rings"] = {"readyPct": READY_PCT.get(str(bucket or ""))}
    return out


def insight(
    metrics: dict[str, Any], *, translator: Translator | None = None, locale: str = "en"
) -> str:
    bucket = metrics.get("bucket", "unknown")
    if translator is not None:
        key = bucket if bucket in {"recovered", "depleted"} else "neutral"
        return "" if bucket == "unknown" else translator.t(f"feed.recovery.insight.{key}", locale)
    return {
        "unknown": "",
        "recovered": "3 of 4 metrics above baseline. Ready to train.",
        "depleted": "3 of 4 metrics below baseline. Prioritize rest today.",
    }.get(bucket, "Recovery metrics near baseline. Moderate training ok.")


async def detail(
    tx: UnitOfWork,
    ctx: DashboardContext,
    *,
    translator: Translator | None = None,
    locale: str = "en",
) -> dict[str, object]:
    metrics_by_day = await daily_metrics(tx, ctx, days=9)
    values = {day: float(m.get("hrv") or 0.0) for day, m in metrics_by_day.items()}
    history = history_points(ctx.last_days(7), values, lambda v: f"{int(v)} ms" if v else "—")
    today = await shape(tx, ctx, ctx.today)
    metrics: dict[str, Any] = {"bucket": today.get("bucket", "unknown") if today else "unknown"}
    for item in (today or {}).get("top3") or []:
        key, value, delta = item.get("key"), item.get("value"), item.get("delta_pct")
        if (
            key and value is not None
        ):  # format_top3 items carry no "key": the legacy detail shows only the bucket
            metrics[key] = round(value, 1)
            if delta is not None:
                metrics[f"{key}_delta_pct"] = round(delta, 1)
    return {
        "agent": "recovery",
        "insight": insight(metrics, translator=translator, locale=locale),
        "metrics": metrics,
        "history": history,
    }
