"""Mood agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from shared.skill_ids import Mood
from .prompt import build_mood_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Mood.LOG,
        name="Log Mood Entry",
        description=(
            "Parse a free-text or explicit '/mood ...' message and record one mood "
            "entry with mood_score, energy, stress, valence, tags, and the raw text."
        ),
        tags=["mood", "journal", "log"],
        examples=[
            "чувствую себя паршиво, голова кипит",
            "/mood 6 устал но продуктивный день",
            "mood good, energetic, focused",
        ],
    ),
    AgentSkill(
        id=Mood.ANALYZE,
        name="Analyze Mood Trend",
        description=(
            "Summarize mood trends over a window (default 7 days): per-day averages, "
            "valence distribution, top tags, comparison with baseline."
        ),
        tags=["mood", "analysis"],
        examples=[
            "какое у меня настроение в этом неделю",
            "analyze my mood this week",
        ],
    ),
    AgentSkill(
        id=Mood.RECOMMENDATIONS,
        name="Get Mood Recommendations",
        description=(
            "Return short actionable advice based on the last 7 days of mood + valence "
            "+ tags. No structured fields."
        ),
        tags=["mood", "recommendations"],
        examples=[
            "что мне делать чтобы чувствовать себя лучше",
            "any mood advice",
        ],
    ),
    AgentSkill(
        id=Mood.COACH_SESSION,
        name="Coach Session Summary",
        description=(
            "Accept a completed coach session transcript and write a single aggregated "
            "mood entry with source_skill='coach_session'. Invoked by the chat coach "
            "loop on session finalization."
        ),
        tags=["mood", "coach"],
        examples=["finalize coach session"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("MOOD_AGENT_URL", "http://agent-mood:8005/")
    return AgentCard(
        protocol_version="0.3.0",
        name="mood-agent",
        description=(
            "Owns mood / journal data: mood scores, energy, stress, tags, free-text "
            "entries, and bounded coach sessions. Provides cross-agent context via "
            "shared vector memory."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_log_mood(message: str, params: dict) -> str:
    return await build_mood_prompt("log_mood", {**params, "message": message})


async def _prompt_analyze(message: str, params: dict) -> str:
    peer = params.get("peer_artifacts")
    return await build_mood_prompt(
        "analyze_mood",
        {**params, "message": message},
        peer_artifacts=peer,
    )


async def _prompt_recommendations(message: str, params: dict) -> str:
    peer = params.get("peer_artifacts")
    return await build_mood_prompt(
        Mood.RECOMMENDATIONS,
        {**params, "message": message},
        peer_artifacts=peer,
    )


async def _prompt_coach_session(message: str, params: dict) -> str:
    return await build_mood_prompt("coach_session", {**params, "message": message})


SKILL_PROMPTS: dict[str, PromptFn] = {
    Mood.LOG: _prompt_log_mood,
    Mood.ANALYZE: _prompt_analyze,
    Mood.RECOMMENDATIONS: _prompt_recommendations,
    Mood.COACH_SESSION: _prompt_coach_session,
}


# Which peer agents this one may consult, and the skill it calls on each.
PEER_SKILLS: dict[str, str] = {
    "sleep": "analyze_sleep",
    "recovery": "analyze_recovery_trend",
    "workout": "analyze_workout",
    "habits": "analyze_habit",
    "medication": "analyze_adherence",
}
