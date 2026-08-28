"""Nutrition agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from shared.skill_ids import Nutrition
from .prompt import build_nutrition_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Nutrition.LOG_MEAL,
        name="Log Meal",
        description="Log a meal from free text and estimate macros (kcal, protein, carbs, fat).",
        tags=["nutrition", "logging"],
        examples=["Съел омлет из 3 яиц и тост", "Had chicken salad for lunch"],
    ),
    AgentSkill(
        id=Nutrition.ANALYZE,
        name="Analyze Nutrition",
        description="Analyze nutrition patterns, macro trends, and meal timing.",
        tags=["nutrition", "analysis"],
        examples=["Как у меня с питанием за неделю?"],
    ),
    AgentSkill(
        id=Nutrition.RECOMMENDATIONS,
        name="Nutrition Recommendations",
        description="Give actionable nutrition recommendations based on recent workouts and macros.",
        tags=["nutrition", "advice"],
    ),
    AgentSkill(
        id=Nutrition.SET_BODY_PROFILE,
        name="Set Body Profile",
        description=(
            "Save the user's body profile (height, age, sex, activity level, calorie goal override) "
            "used to calculate their daily TDEE calorie goal."
        ),
        tags=["nutrition", "profile"],
        examples=[
            "I'm 180cm tall, 30 years old, male, moderately active",
            "My height is 165cm and I'm lightly active",
        ],
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


async def _prompt_set_body_profile(message: str, params: dict) -> str:
    raise NotImplementedError(
        "set_body_profile is direct-handled by the executor "
        "(_DIRECT_SKILLS short-circuit). The prompt builder must not be "
        "called. If you removed the short-circuit, implement this function."
    )


SKILL_PROMPTS: dict[str, PromptFn] = {
    Nutrition.LOG_MEAL: _prompt_log_meal,
    Nutrition.ANALYZE: _prompt_analyze_nutrition,
    Nutrition.RECOMMENDATIONS: _prompt_recommendations,
    Nutrition.SET_BODY_PROFILE: _prompt_set_body_profile,
}


# Which peer agents to consult and which of their skills to invoke.
# Which peer agents this one may consult, and the skill it calls on each.
PEER_SKILLS: dict[str, str] = {
    "workout": "analyze_workout",
    "body": "analyze_body_trend",
    "sleep": "analyze_sleep",
    "mood": "analyze_mood",
    "medication": "analyze_adherence",
}
