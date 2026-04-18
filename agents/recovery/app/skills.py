"""Recovery agent skill declarations + per-skill prompt builders."""
from __future__ import annotations

import os
from typing import Awaitable, Callable

from a2a.types import AgentCapabilities, AgentCard, AgentSkill


SKILLS: list[AgentSkill] = []


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


SKILL_PROMPTS: dict[str, PromptFn] = {}
