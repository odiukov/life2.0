"""Nutrition agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_nutrition_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="log_meal",
        name="Log Meal",
        description="Log a meal from free text and estimate macros (kcal, protein, carbs, fat).",
        tags=["nutrition", "logging"],
        examples=["Съел омлет из 3 яиц и тост", "Had chicken salad for lunch"],
    ),
    AgentSkill(
        id="analyze_nutrition",
        name="Analyze Nutrition",
        description="Analyze nutrition patterns, macro trends, and meal timing.",
        tags=["nutrition", "analysis"],
        examples=["Как у меня с питанием за неделю?"],
    ),
    AgentSkill(
        id="get_nutrition_recommendations",
        name="Nutrition Recommendations",
        description="Give actionable nutrition recommendations based on recent workouts and macros.",
        tags=["nutrition", "advice"],
    ),
    AgentSkill(
        id="briefing",
        name="Daily Briefing Contribution",
        description="Produce a 2-3 sentence nutrition summary for the cross-agent daily briefing.",
        tags=["briefing", "nutrition"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("NUTRITION_AGENT_URL", "http://agent-nutrition:8003/")
    return AgentCard(
        protocol_version="0.3.0",
        name="nutrition-agent",
        description=(
            "Logs meals from free text, parses macros with Claude, analyzes nutrition "
            "patterns, and gives recommendations tailored to recent workout load."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_log_meal(message: str, params: dict) -> str:
    # log_meal is nutrition's specialty: the prompt instructs Claude to parse
    # free-text into structured macros. We pass the raw message as raw_text so
    # the existing prompt template can reference params['raw_text'].
    merged = {**params, "message": message, "raw_text": params.get("raw_text", message)}
    return await build_nutrition_prompt("log_meal", merged)


async def _prompt_analyze_nutrition(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    peer = params.get("peer_artifacts")
    return await build_nutrition_prompt("analyze_nutrition", merged, peer_artifacts=peer)


async def _prompt_recommendations(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    peer = params.get("peer_artifacts")
    return await build_nutrition_prompt("get_recommendations", merged, peer_artifacts=peer)


async def _prompt_briefing(message: str, params: dict) -> str:
    kcal = params.get("kcal", 0)
    protein = params.get("protein_g", 0)
    carbs = params.get("carbs_g", 0)
    fat = params.get("fat_g", 0)

    return (
        "You are a personal nutrition coach providing a morning briefing.\n"
        "Yesterday's nutrition data:\n"
        f"- Total calories: {kcal} kcal\n"
        f"- Protein: {protein}g\n"
        f"- Carbohydrates: {carbs}g\n"
        f"- Fat: {fat}g\n\n"
        "Write a 2-3 sentence plain-text summary (no markdown) of yesterday's nutrition.\n"
        "Note any standouts (high/low protein, surplus/deficit) and implications for today."
    )


SKILL_PROMPTS: dict[str, PromptFn] = {
    "log_meal": _prompt_log_meal,
    "analyze_nutrition": _prompt_analyze_nutrition,
    "get_nutrition_recommendations": _prompt_recommendations,
    "briefing": _prompt_briefing,
}


# Which peer agents to consult and which of their skills to invoke
PEER_SKILLS: dict[str, str] = {
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
}
