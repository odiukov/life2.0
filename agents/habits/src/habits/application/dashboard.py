"""dashboard.card / dashboard.detail for habits. The legacy dashboard rules, not the 3a streak rules."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from shared.dashboard import DashboardContext, empty_card, history_points
from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWork

from habits.application.ports import HabitRepository
from habits.domain.habit import WEEKDAYS, Cadence, Habit, Kind

WINDOW_DAYS = 180


def _expected_on(habit: Habit, day: date) -> bool:
    return habit.cadence is Cadence.DAILY or WEEKDAYS[day.weekday()] in habit.cadence_days


def _complete(habit: Habit, rows: Sequence[Mapping[str, Any]]) -> bool:
    if not rows:
        return False
    if habit.kind is Kind.BOOLEAN:
        return any(r.get("completed") for r in rows)
    total = 0.0
    for r in rows:
        try:
            total += float(r.get("value") or 0)
        except (TypeError, ValueError):
            continue
    target = habit.target_value or 0
    return total >= float(target) if target > 0 else total > 0


def _streak(
    habit: Habit, by_day: Mapping[tuple[str, date], list[Mapping[str, Any]]], today: date
) -> int:
    cursor, count = today, 0
    for _ in range(400):
        if habit.cadence is Cadence.WEEKLY and not _expected_on(habit, cursor):
            cursor -= timedelta(days=1)
            continue
        if not _complete(habit, by_day.get((str(habit.id), cursor), [])):
            break
        count += 1
        cursor -= timedelta(days=1)
    return count


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    out = empty_card()
    habits = await tx.repo(HabitRepository).active()
    if not habits:
        return out
    rows = await tx.repo(HealthLogRepository).recent(
        ctx.user_id, types=["habit"], since=ctx.now - timedelta(days=WINDOW_DAYS)
    )
    by_day: dict[tuple[str, date], list[Mapping[str, Any]]] = {}
    for r in rows:
        if habit_id := r.data.get("habit_id"):
            by_day.setdefault((str(habit_id), ctx.local_date(r.recorded_at)), []).append(r.data)
    expected = completed = 0
    missed: list[str] = []
    for habit in habits:
        if not _expected_on(habit, ctx.yesterday):
            continue
        expected += 1
        if _complete(habit, by_day.get((str(habit.id), ctx.yesterday), [])):
            completed += 1
        else:
            missed.append(habit.name)
    streaks = sorted(
        ((h.name, _streak(h, by_day, ctx.today)) for h in habits),
        key=lambda s: -s[1],
    )
    top = [s for s in streaks if s[1] >= 2][:3]
    if expected > 0:
        pills = []
        if missed:
            pills.append(f"Missed: {missed[0]}")
        if top:
            pills.append(f"Streak: {top[0][0]} {top[0][1]}d")
        out["tile"] = {
            "agent": "habits",
            "label": "Habits",
            "metric": f"{completed}/{expected}",
            "tint": "success" if completed >= expected else "warn",
            "detail": " · ".join(pills) if pills else None,
            "progress": completed / expected,
        }
    return out


def insight(metrics: Mapping[str, Any]) -> str:
    streak, rate, missed = (
        metrics.get("streak", 0),
        metrics.get("completion_7d", 0.0),
        metrics.get("missed_names") or [],
    )
    parts = []
    if streak >= 3:
        parts.append(f"{streak}-day streak.")
    if missed:
        parts.append(f"Missed: {', '.join(missed[:2])}{' and more' if len(missed) > 2 else ''}.")
    elif rate >= 0.8:
        parts.append(f"{int(rate * 100)}% completion this week.")
    return " ".join(parts)


async def detail(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    logs = tx.repo(HealthLogRepository)
    month = await logs.recent(ctx.user_id, types=["habit"], since=ctx.now - timedelta(days=32))
    done_days = {ctx.local_date(r.recorded_at) for r in month if r.data.get("completed")}
    history = history_points(
        ctx.last_days(30), dict.fromkeys(done_days, 1.0), lambda v: "✅" if v else "⬜"
    )
    habits = await tx.repo(HabitRepository).active()
    week = await logs.recent(ctx.user_id, types=["habit"], since=ctx.now - timedelta(days=7))
    completed_days = {ctx.local_date(r.recorded_at) for r in week if r.data.get("completed")}
    streak, cursor = 0, ctx.today
    for _ in range(60):
        if cursor not in completed_days:
            break
        streak += 1
        cursor -= timedelta(days=1)
    rate = len([d for d in completed_days if ctx.today - timedelta(days=6) <= d <= ctx.today]) / 7.0
    done_yesterday = {
        r.data.get("habit_id")
        for r in week
        if ctx.local_date(r.recorded_at) == ctx.yesterday and r.data.get("completed")
    }
    metrics = {
        "streak": streak,
        "completion_7d": round(rate, 2),
        "active_count": len(habits),
        "missed_names": [h.name for h in habits if str(h.id) not in done_yesterday][:3],
    }
    return {"agent": "habits", "insight": insight(metrics), "metrics": metrics, "history": history}
