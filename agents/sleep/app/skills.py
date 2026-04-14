"""Sleep agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_sleep_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="log_sleep",
        name="Log Sleep",
        description="Log a new sleep entry from the user's message.",
        tags=["sleep", "logging"],
        examples=["Спал 7 часов", "Slept 6h30m, woke up tired"],
    ),
    AgentSkill(
        id="analyze_sleep",
        name="Analyze Sleep",
        description="Analyze sleep quality, duration, and recovery trends.",
        tags=["sleep", "analysis"],
        examples=["Как у меня со сном за неделю?"],
    ),
    AgentSkill(
        id="get_sleep_recommendations",
        name="Sleep Recommendations",
        description="Give actionable sleep-improvement recommendations based on history.",
        tags=["sleep", "advice"],
    ),
    AgentSkill(
        id="briefing",
        name="Daily Briefing Contribution",
        description="Produce a 2-3 sentence sleep summary for the cross-agent daily briefing.",
        tags=["briefing", "sleep"],
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


async def _prompt_briefing(message: str, params: dict) -> str:
    dur = params.get("duration_seconds", 0)
    hours = dur // 3600
    minutes = (dur % 3600) // 60
    deep = params.get("deep_sleep_seconds", 0)
    deep_hours = deep // 3600
    deep_minutes = (deep % 3600) // 60
    hrv = params.get("hrv")
    data_lines = [
        f"- Duration: {hours}h {minutes}m",
        f"- Deep sleep: {deep_hours}h {deep_minutes}m",
    ]
    if hrv:
        data_lines.append(f"- HRV: {hrv} ms")
    return (
        "You are a personal sleep health assistant providing a morning briefing.\n"
        "Yesterday's sleep data:\n"
        + "\n".join(data_lines)
        + "\n\nWrite a 2-3 sentence plain-text summary (no markdown) of yesterday's sleep quality.\n"
        "Focus on what stands out and how it may affect today's energy and recovery."
    )


SKILL_PROMPTS: dict[str, PromptFn] = {
    "log_sleep": _prompt_log_sleep,
    "analyze_sleep": _prompt_analyze_sleep,
    "get_sleep_recommendations": _prompt_recommendations,
    "briefing": _prompt_briefing,
}


# Which peer agents to consult and which of their skills to invoke
PEER_SKILLS: dict[str, str] = {
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
}
