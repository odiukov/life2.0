"""Workout agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from shared.skill_ids import Workout
from .prompt import build_workout_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Workout.LOG,
        name="Log Workout",
        description="Log a new workout or training activity from the user's message.",
        tags=["workout", "logging"],
        examples=["Пробежал 5 км", "Did 3x5 squats at 100kg"],
    ),
    AgentSkill(
        id=Workout.ANALYZE,
        name="Analyze Workout",
        description="Analyze training volume, intensity, and recovery trends.",
        tags=["workout", "analysis"],
        examples=["Как у меня с тренировками за неделю?"],
    ),
    AgentSkill(
        id=Workout.RECOMMENDATIONS,
        name="Workout Recommendations",
        description="Give actionable training recommendations based on history and recovery.",
        tags=["workout", "advice"],
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


SKILL_PROMPTS: dict[str, PromptFn] = {
    Workout.LOG: _prompt_log_workout,
    Workout.ANALYZE: _prompt_analyze_workout,
    Workout.RECOMMENDATIONS: _prompt_recommendations,
}


# Which peer agents to consult and which of their skills to invoke.
# Which peer agents this one may consult, and the skill it calls on each.
PEER_SKILLS: dict[str, str] = {
    "recovery": "analyze_recovery_trend",
    "sleep": "analyze_sleep",
    "nutrition": "analyze_nutrition",
    "body": "analyze_body_trend",
    "habits": "analyze_habit",
    "medication": "analyze_adherence",
}
