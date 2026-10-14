"""Pick the skill to run and the peers to consult (structured-output port of shared.intent)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

from pydantic import BaseModel, Field

from shared.ports.llm import LLMError, LLMProvider, LLMTask

# Skills that semantically require this grounding; applied regardless of the LLM's choice.
# Explicit focus_sources from the caller still win.
MANDATORY_CONSULTS: dict[str, list[str]] = {
    "get_workout_recommendations": ["recovery", "sleep"],
    "get_nutrition_recommendations": ["workout"],
    "analyze_mood": ["sleep"],
    "analyze_body_trend": ["nutrition", "workout"],
    "get_recommendations": ["sleep"],
    "get_sleep_recommendations": ["recovery"],
}

ROUTER_SYSTEM = """You are a router for one agent of a personal health assistant.
Pick the skill that matches the user's intent. Pick consult peers ONLY when the user explicitly
references that domain (sleep, nutrition, recovery, ...) or when the skill semantically requires
it. When in doubt, prefer an empty consult list.

Available skills: {skills}
Available peers: {peers}
{mandatory}"""


class IntentDecision(BaseModel):
    skill: str
    consult: list[str] = Field(default_factory=list)


@dataclass(frozen=True, slots=True)
class SkillChoice:
    skill_id: str
    consult: tuple[str, ...]


def _mandatory_block() -> str:
    lines = [f"  {skill} -> {', '.join(peers)}" for skill, peers in MANDATORY_CONSULTS.items()]
    return "Mandatory consults (always added for these skills):\n" + "\n".join(lines)


def _with_mandatory(
    skill_id: str, consult: Sequence[str], candidates: Sequence[str]
) -> tuple[str, ...]:
    out = list(dict.fromkeys(consult))
    for peer in MANDATORY_CONSULTS.get(skill_id, []):
        if peer in candidates and peer not in out:
            out.append(peer)
    return tuple(out)


async def resolve_skill(
    *,
    llm: LLMProvider,
    message: str,
    skills: Sequence[str],
    candidate_peers: Sequence[str],
    requested_skill: str | None,
    focus_sources: Sequence[str] | None,
) -> SkillChoice | None:
    focus = (
        None if focus_sources is None else tuple(p for p in focus_sources if p in candidate_peers)
    )
    if requested_skill in skills:
        assert requested_skill is not None
        if focus is not None:
            return SkillChoice(requested_skill, focus)
        return SkillChoice(requested_skill, _with_mandatory(requested_skill, (), candidate_peers))
    system = ROUTER_SYSTEM.format(
        skills=", ".join(skills),
        peers=", ".join(candidate_peers) or "(none)",
        mandatory=_mandatory_block(),
    )
    try:
        decision = await llm.structured(
            task=LLMTask.FAST, system=system, user=message, schema=IntentDecision
        )
    except LLMError:
        return None
    if decision.skill not in skills:
        return None
    if focus is not None:
        return SkillChoice(decision.skill, focus)
    consult = [p for p in decision.consult if p in candidate_peers]
    return SkillChoice(decision.skill, _with_mandatory(decision.skill, consult, candidate_peers))
