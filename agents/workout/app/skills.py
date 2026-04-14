"""Workout agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_workout_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="log_workout",
        name="Log Workout",
        description="Log a new workout or training activity from the user's message.",
        tags=["workout", "logging"],
        examples=["Пробежал 5 км", "Did 3x5 squats at 100kg"],
    ),
    AgentSkill(
        id="analyze_workout",
        name="Analyze Workout",
        description="Analyze training volume, intensity, and recovery trends.",
        tags=["workout", "analysis"],
        examples=["Как у меня с тренировками за неделю?"],
    ),
    AgentSkill(
        id="get_workout_recommendations",
        name="Workout Recommendations",
        description="Give actionable training recommendations based on history and recovery.",
        tags=["workout", "advice"],
    ),
    AgentSkill(
        id="briefing",
        name="Daily Briefing Contribution",
        description="Produce a 2-3 sentence workout summary for the cross-agent daily briefing.",
        tags=["briefing", "workout"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("WORKOUT_AGENT_URL", "http://agent-workout:8002/")
    return AgentCard(
        protocol_version="0.3.0",
        name="workout-agent",
        description="Tracks workouts, activities, training load",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_log_workout(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    return await build_workout_prompt("log_workout", merged)


async def _prompt_analyze_workout(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    peer = params.get("peer_artifacts")
    return await build_workout_prompt("analyze_workout", merged, peer_artifacts=peer)


async def _prompt_recommendations(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    peer = params.get("peer_artifacts")
    return await build_workout_prompt("get_recommendations", merged, peer_artifacts=peer)


async def _prompt_briefing(message: str, params: dict) -> str:
    name = params.get("first_name") or params.get("first_type") or "Workout"
    dist_km = params.get("total_distance_meters", 0) / 1000
    kcal = params.get("total_calories", 0)
    count = params.get("activity_count", 1)

    data_lines = [f"- Activity: {name}"]
    if dist_km > 0:
        data_lines.append(f"- Distance: {dist_km:.1f} km")
    data_lines.append(f"- Calories burned: {kcal} kcal")
    if count > 1:
        data_lines.append(f"- Activities: {count}")

    return (
        "You are a personal fitness coach providing a morning briefing.\n"
        "Yesterday's workout data:\n"
        + "\n".join(data_lines)
        + "\n\nWrite a 2-3 sentence plain-text summary (no markdown) of yesterday's workout.\n"
        "Note training load and how it may affect today's readiness."
    )


SKILL_PROMPTS: dict[str, PromptFn] = {
    "log_workout": _prompt_log_workout,
    "analyze_workout": _prompt_analyze_workout,
    "get_workout_recommendations": _prompt_recommendations,
    "briefing": _prompt_briefing,
}


# Which peer agents to consult and which of their skills to invoke
PEER_SKILLS: dict[str, str] = {
    "sleep": "analyze_sleep",
    "nutrition": "analyze_nutrition",
}
