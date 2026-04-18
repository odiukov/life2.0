"""Recovery agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_recovery_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="get_readiness",
        name="Get Today's Readiness",
        description=(
            "Return today's recovery snapshot: coarse bucket (recovered / neutral "
            "/ depleted / unknown) + HRV, RHR, stress, body-battery with trend "
            "deltas. Bucket rule is deterministic (shared.recovery.compute_bucket); "
            "LLM formats the human-readable response on top."
        ),
        tags=["recovery", "readiness", "query"],
        examples=[
            "как я восстанавливаюсь",
            "am I recovered today",
            "readiness",
        ],
    ),
    AgentSkill(
        id="analyze_recovery_trend",
        name="Analyze Recovery Trend",
        description=(
            "Analyze recovery metrics over a window (default 7 days): per-metric "
            "trend direction, outlier days, correlations between HRV / stress / RHR."
        ),
        tags=["recovery", "analysis"],
        examples=[
            "recovery trend this week",
            "как менялся мой HRV за неделю",
        ],
    ),
    AgentSkill(
        id="get_recommendations",
        name="Get Recovery Recommendations",
        description=(
            "2–3 actionable recommendations based on last 7 days of recovery data. "
            "Tone is practical, not prescriptive."
        ),
        tags=["recovery", "recommendations"],
        examples=[
            "what should I do to recover better",
            "посоветуй что делать если HRV просел",
        ],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("RECOVERY_AGENT_URL", "http://agent-recovery:8007/")
    return AgentCard(
        protocol_version="0.3.0",
        name="recovery-agent",
        description=(
            "Read-only analytical lens over Garmin-synced recovery metrics "
            "(HRV, RHR, stress, body battery). Produces bucket (recovered / "
            "neutral / depleted / unknown), trend analysis, and recommendations."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_readiness(message: str, params: dict) -> str:
    return await build_recovery_prompt("get_readiness", {**params, "message": message})


async def _prompt_trend(message: str, params: dict) -> str:
    return await build_recovery_prompt("analyze_recovery_trend", {**params, "message": message})


async def _prompt_recommendations(message: str, params: dict) -> str:
    return await build_recovery_prompt("get_recommendations", {**params, "message": message})


SKILL_PROMPTS: dict[str, PromptFn] = {
    "get_readiness": _prompt_readiness,
    "analyze_recovery_trend": _prompt_trend,
    "get_recommendations": _prompt_recommendations,
}
