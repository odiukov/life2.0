"""dashboard.card / dashboard.detail for mood (and the mood ring). Ported from the legacy dashboard."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, timedelta
from typing import Any

from shared.dashboard import DashboardContext, empty_card, history_points, pg_round
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWork

MOOD = "mood"


def _f(value: object) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _mean(rows: Sequence[HealthLogRow], key: str) -> float | None:
    values = [v for r in rows if (v := _f(r.data.get(key))) is not None]
    return sum(values) / len(values) if values else None


async def _yesterday(
    tx: UnitOfWork, ctx: DashboardContext, *, agent: str | None
) -> list[HealthLogRow]:
    start, end = ctx.bounds(ctx.yesterday)
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=[MOOD], since=start, agent=agent
    )
    return [r for r in rows if r.recorded_at < end]


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    rows = await _yesterday(tx, ctx, agent=None)
    out = empty_card()
    average = _mean(rows, "mood_score")
    score = round(average, 1) if average is not None else None
    if rows and score is not None:
        stress, energy = _mean(rows, "stress"), _mean(rows, "energy")
        pills = []
        if stress is not None:
            pills.append(f"Stress {round(stress, 1):.1f}")
        if energy is not None:
            pills.append(f"Energy {round(energy, 1):.1f}")
        pills.append(f"{len(rows)} entries")
        out["tile"] = {
            "agent": "mood",
            "label": "Mood",
            "metric": f"{score:.1f}/10",
            "tint": "success" if score >= 7 else "warn",
            "detail": " · ".join(pills),
            "progress": score / 10.0,
        }
    out["rings"] = {"moodPct": None if score is None else min(100, round(score / 10.0 * 100))}
    return out


def insight(history: list[dict[str, object]]) -> str:
    values = [float(h["value"]) for h in history if float(h["value"]) > 0]  # type: ignore[arg-type]
    if len(values) < 4:
        return ""
    mid = len(values) // 2
    diff = sum(values[mid:]) / len(values[mid:]) - sum(values[:mid]) / mid
    if diff > 0.5:
        return f"Score trending up +{diff:.1f} pts over the last {len(values)} days."
    if diff < -0.5:
        return f"Score trending down {diff:.1f} pts over the last {len(values)} days."
    return "Mood stable over the last week."


async def detail(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=[MOOD], since=ctx.now - timedelta(days=9), agent="mood"
    )
    by_day: dict[date, list[HealthLogRow]] = {}
    for r in rows:
        by_day.setdefault(ctx.local_date(r.recorded_at), []).append(r)
    values = {
        day: pg_round(m, 1)
        for day, day_rows in by_day.items()
        if (m := _mean(day_rows, "mood_score")) is not None
    }
    history = history_points(ctx.last_days(7), values, lambda v: f"{v:.1f}" if v > 0 else "—")
    yesterday = await _yesterday(tx, ctx, agent="mood")
    metrics: dict[str, Any] = {}
    if (score := _mean(yesterday, "mood_score")) is not None:
        metrics["score"] = pg_round(score, 1)
        if (energy := _mean(yesterday, "energy")) is not None:
            metrics["energy"] = pg_round(energy, 1)
        if (stress := _mean(yesterday, "stress")) is not None:
            metrics["stress"] = pg_round(stress, 1)
        if valence := yesterday[0].data.get("valence"):
            metrics["valence"] = valence
        tags = yesterday[0].data.get("tags")
        if isinstance(tags, list) and tags:
            metrics["top_tag"] = tags[0]
    return {"agent": "mood", "insight": insight(history), "metrics": metrics, "history": history}
