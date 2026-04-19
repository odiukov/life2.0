"""Medication agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill

from .prompt import build_medication_prompt


SKILLS: list[AgentSkill] = [
    AgentSkill(
        id="define_medication",
        name="Define Medication",
        description=(
            "Parse free text into a structured medication definition: name "
            "(kebab-case), dose (e.g. '200mg'), schedule (free-text e.g. "
            "'daily 21:00' or 'mon,wed,fri morning'), optional notes. Inserts "
            "a row in the medications table."
        ),
        tags=["medication", "define"],
        examples=[
            "магний 200мг каждый вечер в 21:00",
            "vitamin D 2000IU every morning",
            "iron 25mg mon/wed/fri",
        ],
    ),
    AgentSkill(
        id="log_taken",
        name="Log Medication Taken",
        description=(
            "Record a single dose taken. Accepts {name} (resolved via registry "
            "with name normalization) and optional {dose_override, note}."
        ),
        tags=["medication", "log"],
        examples=[
            "/med magnesium",
            "выпил магний вечером",
            "took iron with breakfast",
        ],
    ),
    AgentSkill(
        id="list_active",
        name="List Active Medications",
        description=(
            "Deterministic list of active medications with last-taken recency. "
            "Used by /med (no args) and the morning briefing."
        ),
        tags=["medication", "list"],
        examples=["/med list", "what am I currently taking"],
    ),
    AgentSkill(
        id="analyze_adherence",
        name="Analyze Adherence",
        description=(
            "Compute adherence window (default 14 days): expected doses from "
            "schedule × actual logs from health_logs → percentage + missed days + "
            "streak. Aggregations in SQL, final summary via LLM."
        ),
        tags=["medication", "analysis"],
        examples=[
            "how's my medication adherence",
            "did I miss any doses last week",
        ],
    ),
    AgentSkill(
        id="archive_medication",
        name="Archive Medication",
        description=(
            "Soft-delete a medication (set archived_at). History in health_logs "
            "is preserved via the denormalized `name` field."
        ),
        tags=["medication", "archive"],
        examples=["/med stop magnesium", "stop tracking iron"],
    ),
]


def build_agent_card() -> AgentCard:
    url = os.environ.get("MEDICATION_AGENT_URL", "http://agent-medication:8008/")
    return AgentCard(
        protocol_version="0.3.0",
        name="medication-agent",
        description=(
            "Owns medication/supplement definitions and intake logs: creates "
            "schedules, records doses taken, computes adherence, and produces "
            "briefing alerts when doses are missed."
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
    return await build_medication_prompt("define_medication", {**params, "message": message})


async def _prompt_log(message: str, params: dict) -> str:
    return await build_medication_prompt("log_taken", {**params, "message": message})


async def _prompt_list(message: str, params: dict) -> str:
    return await build_medication_prompt("list_active", {**params, "message": message})


async def _prompt_analyze(message: str, params: dict) -> str:
    return await build_medication_prompt("analyze_adherence", {**params, "message": message})


async def _prompt_archive(message: str, params: dict) -> str:
    return await build_medication_prompt("archive_medication", {**params, "message": message})


SKILL_PROMPTS: dict[str, PromptFn] = {
    "define_medication": _prompt_define,
    "log_taken": _prompt_log,
    "list_active": _prompt_list,
    "analyze_adherence": _prompt_analyze,
    "archive_medication": _prompt_archive,
}
