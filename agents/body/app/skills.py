"""Body agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_body_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="get_latest_body",
        name="Get Latest Body Composition",
        description="Return the most recent weight, body fat %, muscle and related metrics.",
        tags=["body", "weight", "query"],
        examples=["сколько я вешу", "what's my weight", "current body fat"],
    ),
    AgentSkill(
        id="analyze_body_trend",
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
    return await build_body_prompt("get_latest_body", {**params, "message": message})


async def _prompt_analyze(message: str, params: dict) -> str:
    return await build_body_prompt("analyze_body_trend", {**params, "message": message})


SKILL_PROMPTS: dict[str, PromptFn] = {
    "get_latest_body": _prompt_get_latest,
    "analyze_body_trend": _prompt_analyze,
}
