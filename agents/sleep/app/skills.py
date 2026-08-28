"""Sleep agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from shared.skill_ids import Sleep
from .prompt import build_sleep_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Sleep.LOG,
        name="Log Sleep",
        description="Log a new sleep entry from the user's message.",
        tags=["sleep", "logging"],
        examples=["Спал 7 часов", "Slept 6h30m, woke up tired"],
    ),
    AgentSkill(
        id=Sleep.ANALYZE,
        name="Analyze Sleep",
        description="Analyze sleep quality, duration, and recovery trends.",
        tags=["sleep", "analysis"],
        examples=["Как у меня со сном за неделю?"],
    ),
    AgentSkill(
        id=Sleep.RECOMMENDATIONS,
        name="Sleep Recommendations",
        description="Give actionable sleep-improvement recommendations based on history.",
        tags=["sleep", "advice"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("SLEEP_AGENT_URL", "http://agent-sleep:8001/")
    return AgentCard(
        protocol_version="0.3.0",
        name="sleep-agent",
        description="Tracks sleep patterns, analyzes quality, and gives recommendations.",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_log_sleep(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    return await build_sleep_prompt("log_sleep", merged)


async def _prompt_analyze_sleep(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    peer = params.get("peer_artifacts")
    return await build_sleep_prompt("analyze_sleep", merged, peer_artifacts=peer)


async def _prompt_recommendations(message: str, params: dict) -> str:
    merged = {**params, "message": message}
    peer = params.get("peer_artifacts")
    return await build_sleep_prompt("get_recommendations", merged, peer_artifacts=peer)


SKILL_PROMPTS: dict[str, PromptFn] = {
    Sleep.LOG: _prompt_log_sleep,
    Sleep.ANALYZE: _prompt_analyze_sleep,
    Sleep.RECOMMENDATIONS: _prompt_recommendations,
}


# Which peer agents to consult and which of their skills to invoke.
# Which peer agents this one may consult, and the skill it calls on each.
PEER_SKILLS: dict[str, str] = {
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
    "recovery": "analyze_recovery_trend",
    "mood": "analyze_mood",
    "medication": "analyze_adherence",
}
