"""Habits agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_habits_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="define_habit",
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
        id="log_habit_check",
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
        id="analyze_habit",
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
        id="get_streak_summary",
        name="Get Streak Summary",
        description=(
            "Deterministic one-liner across all active habits showing current streaks "
            "and (for quantitative) today's progress vs target. Used by /habits and "
            "the morning briefing."
        ),
        tags=["habits", "summary"],
        examples=["streak summary", "/habits"],
    ),
    AgentSkill(
        id="archive_habit",
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
            "(boolean or quantitative), calculates streaks, and produces briefing summaries."
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
    return await build_habits_prompt("analyze_habit", {**params, "message": message})


async def _prompt_streak(message: str, params: dict) -> str:
    return await build_habits_prompt("get_streak_summary", {**params, "message": message})


async def _prompt_archive(message: str, params: dict) -> str:
    return await build_habits_prompt("archive_habit", {**params, "message": message})


SKILL_PROMPTS: dict[str, PromptFn] = {
    "define_habit": _prompt_define,
    "log_habit_check": _prompt_log_check,
    "analyze_habit": _prompt_analyze,
    "get_streak_summary": _prompt_streak,
    "archive_habit": _prompt_archive,
}
