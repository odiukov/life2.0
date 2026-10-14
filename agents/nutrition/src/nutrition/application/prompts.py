"""Nutrition analysis prompt built from typed inputs."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from shared.analysis.prompt import PromptSection
from shared.domain.energy import BodyProfile

from nutrition.application.models import BodyComposition
from nutrition.domain.meal import Macros, Meal

AnalysisMode = Literal["analyze_nutrition", "get_recommendations"]
PEER_ORDER = ("workout", "body", "sleep", "mood", "medication")

SKILL_TAIL: dict[AnalysisMode, str] = {
    "analyze_nutrition": (
        "Respond in 6–10 lines plain text: (1) intake vs goal grounded in the data, (2) protein "
        "floor and carb-around-training observations, (3) meal-timing pattern. Redirect "
        "cross-domain action to peers. No markdown."
    ),
    "get_recommendations": (
        "Respond in 4–6 lines plain text: 2–3 concrete nutrition actions for today + the 'why' "
        "grounded in the data and recent training. Redirect training prescriptions to /workout. "
        "No markdown."
    ),
}


def _macros(m: Macros) -> str:
    return f"{round(m.kcal)} kcal | P:{round(m.protein_g, 1)}g C:{round(m.carbs_g, 1)}g F:{round(m.fat_g, 1)}g"


def _profile(profile: BodyProfile) -> str:
    parts = [f"{key}={value}" for key, value in profile.to_mapping().items()]
    return " | ".join(parts) if parts else "Not set."


def _meal_line(meal: Meal, zone: ZoneInfo) -> str:
    items = ", ".join(
        f"{item.name} {round(item.amount_g)}g" if item.amount_g else item.name
        for item in meal.items
    )
    meal_type = meal.meal_type.value if meal.meal_type else "meal"
    local_day = meal.recorded_at.astimezone(zone).date()
    return f"- {local_day} | {meal_type} | {meal.source} | {items} → {_macros(meal.totals)}"


def _body(body: BodyComposition | None) -> str:
    if body is None:
        return "No body composition measurements yet."
    return (
        f"- {body.recorded_at.date()} | weight={body.weight_kg}kg | fat={body.body_fat_pct}% "
        f"| BMR={body.bmr_kcal}kcal"
    )


def analysis_sections(
    *,
    day: date,
    is_today: bool,
    zone: ZoneInfo,
    profile: BodyProfile,
    intake: Macros,
    goal: int | None,
    recent: Sequence[Meal],
    body: BodyComposition | None,
) -> list[PromptSection]:
    label = "Today" if is_today else f"Day ({day})"
    goal_text = f"{goal} kcal" if goal else "unknown"
    remaining = f"{goal - round(intake.kcal)} kcal remaining" if goal else "goal unknown"
    recent_text = "\n".join(_meal_line(m, zone) for m in recent) or "No recent meals."
    return [
        PromptSection("User profile", _profile(profile)),
        PromptSection(
            f"{label} ({day}) intake (Yazio and chat)",
            f"- Eaten: {_macros(intake)}\n- Goal: {goal_text}\n- {remaining}",
        ),
        PromptSection(
            "Recent meals (last 10, may span several days — each line shows its date)", recent_text
        ),
        PromptSection("Latest body composition (cross-context)", _body(body), after_peers=True),
    ]
