"""dashboard.card / dashboard.detail for nutrition. Ported from the legacy dashboard."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import date, timedelta
from typing import Any

from shared.dashboard import DashboardContext, empty_card, history_points, pg_round
from shared.domain.energy import ActivityLevel, Sex, bmr_mifflin_st_jeor, tdee
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.profile import BodyProfileRepository
from shared.ports.translator import Translator
from shared.ports.uow import UnitOfWork

MEAL = "meal"


def _f(value: object) -> float | None:
    try:
        return None if value is None or isinstance(value, bool) else float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _total(rows: Sequence[HealthLogRow], key: str) -> float | None:
    values = [v for r in rows if (v := _f((r.data.get("totals") or {}).get(key))) is not None]
    return sum(values) if values else None


def compute_tdee(weight: float, height: float, age: int, sex: str, activity: str) -> int:
    bmr = bmr_mifflin_st_jeor(
        weight_kg=weight, height_cm=height, age=age, sex=Sex.MALE if sex == "male" else Sex.FEMALE
    )
    return tdee(bmr, ActivityLevel.parse(activity))


def _goal(profile: Mapping[str, Any], weight: object) -> int | None:
    if override := profile.get("calorie_goal_override"):
        return int(override)
    if all(
        [
            weight,
            profile.get("height_cm"),
            profile.get("age"),
            profile.get("sex"),
            profile.get("activity_level"),
        ]
    ):
        return compute_tdee(
            float(weight),  # type: ignore[arg-type]
            float(profile["height_cm"]),
            int(profile["age"]),
            str(profile["sex"]),
            str(profile["activity_level"]),
        )
    return None


async def day_nutrition(tx: UnitOfWork, ctx: DashboardContext, day: date) -> dict[str, Any] | None:
    logs = tx.repo(HealthLogRepository)
    start, end = ctx.bounds(day)
    meals = [
        r
        for r in await logs.recent(ctx.user_id, types=[MEAL], since=start, agent="nutrition")
        if r.recorded_at < end and r.source == "yazio"
    ]
    kcal = _total(meals, "kcal")
    if kcal is not None:
        return {
            "kcal": round(kcal),
            "protein_g": round(_total(meals, "protein_g") or 0),
            "carbs_g": round(_total(meals, "carbs_g") or 0),
            "fat_g": round(_total(meals, "fat_g") or 0),
            "source": "Yazio",
        }
    stats = [
        r
        for r in await logs.recent(ctx.user_id, types=["daily_stats"], since=start)
        if r.recorded_at < end
    ]
    if stats and (energy := _f(stats[0].data.get("dietaryEnergyConsumed"))):
        d = stats[0].data
        return {
            "kcal": round(energy),
            "protein_g": round(_f(d.get("dietaryProtein")) or 0),
            "carbs_g": round(_f(d.get("dietaryCarbohydrates")) or 0),
            "fat_g": round(_f(d.get("dietaryFatTotal")) or 0),
            "source": "Apple Health",
        }
    return None


async def card(tx: UnitOfWork, ctx: DashboardContext) -> dict[str, object]:
    today = await day_nutrition(tx, ctx, ctx.today)
    is_today = bool(today and today.get("kcal"))
    nutrition = today if is_today else await day_nutrition(tx, ctx, ctx.yesterday)
    out = empty_card()
    if nutrition is None:
        return out
    profile = await tx.repo(BodyProfileRepository).get(ctx.user_id)
    kcal = int(nutrition["kcal"])
    pills = [
        f"P {int(nutrition['protein_g'])}g",
        f"C {int(nutrition['carbs_g'])}g",
        f"F {int(nutrition['fat_g'])}g",
    ]
    goal: int | None = None
    try:
        weight = profile.get("weight_kg")
        if weight is None:
            latest = await tx.repo(HealthLogRepository).recent(
                ctx.user_id, types=["body_composition"], limit=1
            )
            weight = latest[0].data.get("weight_kg") if latest else None
        goal = _goal(profile, weight)
    except (TypeError, ValueError):
        goal = None
    if goal:
        pills.append(f"Goal {goal} kcal")
    out["tile"] = {
        "agent": "nutrition",
        "label": "Nutrition",
        "metric": f"{kcal} kcal",
        "tint": "neutral",
        "detail": " · ".join(pills),
        "progress": min(kcal / goal, 1.0) if goal else None,
    }
    macros_weight = profile.get("weight_kg") or 75.0  # the legacy featured block ignores body logs
    try:
        kcal_goal = _goal(profile, macros_weight) or 0
    except (TypeError, ValueError):
        kcal_goal = 0
    out["featured"] = {
        "kcalConsumed": kcal,
        "kcalGoal": kcal_goal or 2000,
        "proteinG": int(nutrition.get("protein_g") or 0),
        "proteinGoalG": max(1, round(float(macros_weight) * 1.8)),  # type: ignore[arg-type]
        "carbsG": int(nutrition.get("carbs_g") or 0),
        "carbsGoalG": max(1, round(float(macros_weight) * 4.0)),  # type: ignore[arg-type]
        "fatG": int(nutrition.get("fat_g") or 0),
        "fatGoalG": max(1, round(float(macros_weight) * 1.0)),  # type: ignore[arg-type]
        "source": nutrition.get("source", "Yazio"),
        "nutritionDate": "today" if is_today else "yesterday",
    }
    return out


def _meal(row: HealthLogRow) -> dict[str, object]:
    data = row.data
    meal_type = str(data.get("meal_type") or "meal")
    items = [
        str(i.get("name"))
        for i in data.get("items") or []
        if isinstance(i, Mapping) and i.get("name")
    ]
    return {
        "meal_type": meal_type,
        "label": meal_type.replace("_", " ").title(),
        "items": items,
        "kcal": round(_f((data.get("totals") or {}).get("kcal")) or 0),
        "recorded_at": row.recorded_at.isoformat(),
    }


def insight(
    history: list[dict[str, object]],
    metrics: Mapping[str, Any],
    *,
    translator: Translator | None = None,
    locale: str = "en",
) -> str:
    protein, goal_g = metrics.get("protein_g"), metrics.get("protein_goal_g")
    if protein is not None and goal_g and protein < goal_g * 0.8:
        if translator is not None:
            return translator.t("feed.nutrition.insight.below", locale, grams=int(goal_g - protein))
        return f"Protein below goal by {int(goal_g - protein)}g today."
    values = [float(h["value"]) for h in history if float(h["value"]) > 0]  # type: ignore[arg-type]
    if len(values) < 3:
        return ""
    average = sum(values) / len(values)
    goal = metrics.get("goal_kcal") or average
    days_over = sum(1 for v in values if v >= goal * 0.9)
    if days_over >= 5 and translator is not None:
        return translator.t(
            "feed.nutrition.insight.track", locale, count=days_over, days=len(values)
        )
    return f"On track {days_over} of {len(values)} days." if days_over >= 5 else ""


async def detail(
    tx: UnitOfWork,
    ctx: DashboardContext,
    *,
    translator: Translator | None = None,
    locale: str = "en",
) -> dict[str, object]:
    logs = tx.repo(HealthLogRepository)
    rows = await logs.recent(
        ctx.user_id, types=[MEAL], since=ctx.now - timedelta(days=9), agent="nutrition"
    )
    per_day: dict[date, float] = {}
    for r in rows:
        if (kcal := _f((r.data.get("totals") or {}).get("kcal"))) is not None:
            day = ctx.local_date(r.recorded_at)
            per_day[day] = per_day.get(day, 0.0) + kcal
    values = {day: float(int(pg_round(total))) for day, total in per_day.items()}
    history = history_points(ctx.last_days(7), values, lambda v: f"{int(v)} kcal" if v > 0 else "—")
    start, end = ctx.bounds(ctx.today)
    today_rows = [r for r in rows if start <= r.recorded_at < end]
    metrics: dict[str, Any] = {}
    kcal_today = _total(today_rows, "kcal")
    if kcal_today is not None:
        metrics["protein_g"] = int(pg_round(_total(today_rows, "protein_g") or 0))
        metrics["carbs_g"] = int(pg_round(_total(today_rows, "carbs_g") or 0))
        metrics["fat_g"] = int(pg_round(_total(today_rows, "fat_g") or 0))
        metrics["kcal"] = int(pg_round(kcal_today))
    meals = [
        _meal(r)
        for r in sorted((r for r in today_rows if r.source == "yazio"), key=lambda r: r.recorded_at)
    ]
    profile = await tx.repo(BodyProfileRepository).get(ctx.user_id)
    if profile.get("tdee"):
        metrics["goal_kcal"] = int(profile["tdee"])  # type: ignore[call-overload]
    if profile.get("protein_goal_g"):
        metrics["protein_goal_g"] = int(profile["protein_goal_g"])  # type: ignore[call-overload]
    return {
        "agent": "nutrition",
        "insight": insight(history, metrics, translator=translator, locale=locale),
        "metrics": metrics,
        "history": history,
        "meals": meals,
    }
