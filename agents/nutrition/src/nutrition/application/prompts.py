"""Nutrition analysis prompt built from typed inputs."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date
from typing import Literal
from zoneinfo import ZoneInfo

from shared.analysis.chip_rules import PEER_CHIP_RULES
from shared.analysis.grounding import GROUNDING_RULES
from shared.analysis.personas import IDENTITY, VOCAB
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


@dataclass(frozen=True, slots=True)
class AnalysisInputs:
    mode: AnalysisMode
    day: date
    is_today: bool
    zone: ZoneInfo
    profile: BodyProfile
    intake: Macros
    goal: int | None
    recent: Sequence[Meal]
    body: BodyComposition | None
    peers: Mapping[str, str]
    memories: Sequence[str]
    message: str


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


def build_analysis_prompt(inputs: AnalysisInputs) -> tuple[str, str]:
    system = (
        f"{IDENTITY['nutrition']}\n\n"
        f"## Vocabulary you may invoke (only when grounded by data)\n{VOCAB['nutrition']}\n\n"
        f"{GROUNDING_RULES}"
    )
    label = "Today" if inputs.is_today else f"Day ({inputs.day})"
    goal = f"{inputs.goal} kcal" if inputs.goal else "unknown"
    remaining = (
        f"{inputs.goal - round(inputs.intake.kcal)} kcal remaining"
        if inputs.goal
        else "goal unknown"
    )
    recent = "\n".join(_meal_line(m, inputs.zone) for m in inputs.recent) or "No recent meals."
    peer_chunks = [
        f"### {name}\n{inputs.peers[name]}"
        for name in PEER_ORDER
        if inputs.peers.get(name, "").strip()
    ]
    peer_section = "\n## Peer context\n" + "\n\n".join(peer_chunks) + "\n" if peer_chunks else ""
    memories = "\n".join(f"- {text}" for text in inputs.memories) or "No relevant memories."
    sections = [
        f"## User profile\n{_profile(inputs.profile)}",
        f"## {label} ({inputs.day}) intake (Yazio and chat)\n- Eaten: {_macros(inputs.intake)}\n"
        f"- Goal: {goal}\n- {remaining}",
        "## Recent meals (last 10, may span several days — each line shows its date)\n" + recent,
        peer_section,
        f"## Latest body composition (cross-context)\n{_body(inputs.body)}",
        f"## Memories\n{memories}",
        f"## User request\nTask: {inputs.mode}\nMessage: {inputs.message}",
        PEER_CHIP_RULES if peer_chunks else "",
        SKILL_TAIL[inputs.mode],
    ]
    return system, "\n\n".join(section for section in sections if section)
