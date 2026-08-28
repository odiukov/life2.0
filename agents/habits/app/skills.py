"""Habits agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from shared.skill_ids import Habits
from .prompt import build_habits_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Habits.DEFINE,
        name="Define Habit",
        description=(
            "Parse free text (from '/habit new ...') into a structured habit definition "
            "with name (lowercase kebab-case), kind (boolean|quantitative), cadence "
            "(daily or specific weekdays), optional target_value + unit. Inserts a row "
            "in the habits table."
        ),
        tags=["habits", "define"],
        examples=[
            "медитация 20 минут каждый день",
            "cold shower every morning",
            "зал по пн/ср/пт",
        ],
    ),
    AgentSkill(
        id=Habits.LOG_CHECK,
        name="Log Habit Check-in",
        description=(
            "Record one check-in for an existing habit. Accepts either {habit_id} "
            "(from inline-button callback) or {name} (resolved via registry with "
            "name normalization). Optional value/unit/note."
        ),
        tags=["habits", "log"],
        examples=[
            "/habit meditation",
            "/habit meditation 15min",
            "mark cold-shower done",
        ],
    ),
    AgentSkill(
        id=Habits.ANALYZE,
        name="Analyze Habit Adherence",
        description=(
            "Summarize adherence over a window (default 7 days): % completion, "
            "current streak, longest streak, missed days, value distribution for "
            "quantitative habits. Aggregations in SQL, final text via LLM."
        ),
        tags=["habits", "analysis"],
        examples=[
            "how am I doing on my habits this week",
            "meditation streak",
        ],
    ),
    AgentSkill(
        id=Habits.STREAK_SUMMARY,
        name="Get Streak Summary",
        description=(
            "Deterministic one-liner across all active habits showing current streaks "
            "and (for quantitative) today's progress vs target. Used by /habits."
        ),
        tags=["habits", "summary"],
        examples=["streak summary", "/habits"],
    ),
    AgentSkill(
        id=Habits.ARCHIVE,
        name="Archive Habit",
        description=(
            "Soft-delete a habit (set archived_at). History in health_logs is preserved "
            "via the denormalized `name` field."
        ),
        tags=["habits", "archive"],
        examples=["/habit stop meditation", "stop tracking cold-shower"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("HABITS_AGENT_URL", "http://agent-habits:8006/")
    return AgentCard(
        protocol_version="0.3.0",
        name="habits-agent",
        description=(
            "Owns habit definitions and daily check-ins: creates habits, logs completions "
            "(boolean or quantitative), and calculates streaks."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PromptFn = Callable[[str, dict], Awaitable[str]]


async def _prompt_define(message: str, params: dict) -> str:
    return await build_habits_prompt("define_habit", {**params, "message": message})


async def _prompt_log_check(message: str, params: dict) -> str:
    return await build_habits_prompt("log_habit_check", {**params, "message": message})


async def _prompt_analyze(message: str, params: dict) -> str:
    peer = params.get("peer_artifacts")
    return await build_habits_prompt(
        "analyze_habit",
        {**params, "message": message},
        peer_artifacts=peer,
    )


async def _prompt_streak(message: str, params: dict) -> str:
    return await build_habits_prompt("get_streak_summary", {**params, "message": message})


async def _prompt_archive(message: str, params: dict) -> str:
    return await build_habits_prompt("archive_habit", {**params, "message": message})


SKILL_PROMPTS: dict[str, PromptFn] = {
    Habits.DEFINE: _prompt_define,
    Habits.LOG_CHECK: _prompt_log_check,
    Habits.ANALYZE: _prompt_analyze,
    Habits.STREAK_SUMMARY: _prompt_streak,
    Habits.ARCHIVE: _prompt_archive,
}


# Which peer agents this one may consult, and the skill it calls on each.
# Only analyze_habit uses peer artifacts — the other 4 skills are deterministic
# or JSON parsers.
PEER_SKILLS: dict[str, str] = {
    "mood": "analyze_mood",
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
}
