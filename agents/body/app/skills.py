"""Body agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from shared.skill_ids import Body
from .prompt import build_body_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Body.GET_LATEST,
        name="Get Latest Body Composition",
        description="Return the most recent weight, body fat %, muscle and related metrics.",
        tags=["body", "weight", "query"],
        examples=["сколько я вешу", "what's my weight", "current body fat"],
    ),
    AgentSkill(
        id=Body.ANALYZE_TREND,
        name="Analyze Body Trend",
        description="Analyze weight / fat / muscle dynamics and correlate with nutrition and training.",
        tags=["body", "analysis"],
        examples=["проанализируй историю веса", "how has my body composition changed"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("BODY_AGENT_URL", "http://agent-body:8004/")
    return AgentCard(
        protocol_version="0.3.0",
        name="body-agent",
        description=(
            "Owns body-composition data (weight, fat %, muscle, BMR, visceral fat, body age) "
            "ingested from ViHealth/LePulse scales. Answers current-state queries and trend analyses."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_get_latest(message: str, params: dict) -> str:
    peer = params.get("peer_artifacts")
    return await build_body_prompt(
        "get_latest_body",
        {**params, "message": message},
        peer_artifacts=peer,
    )


async def _prompt_analyze(message: str, params: dict) -> str:
    peer = params.get("peer_artifacts")
    return await build_body_prompt(
        "analyze_body_trend",
        {**params, "message": message},
        peer_artifacts=peer,
    )


SKILL_PROMPTS: dict[str, PromptFn] = {
    Body.GET_LATEST: _prompt_get_latest,
    Body.ANALYZE_TREND: _prompt_analyze,
}


# Which peer agents this one may consult, and the skill it calls on each.
PEER_SKILLS: dict[str, str] = {
    "nutrition": "analyze_nutrition",
    "workout": "analyze_workout",
    "recovery": "analyze_recovery_trend",
}
