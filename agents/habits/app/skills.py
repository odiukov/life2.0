"""Habits agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill


SKILLS: list[AgentSkill] = []


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


SKILL_PROMPTS: dict[str, PromptFn] = {}
