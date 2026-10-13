"""Single LLM-driven intent extraction step. Replaces per-agent _decide_peers
and _infer_skill_via_llm in workout/sleep/nutrition executors. Returns the skill
ID plus the peer agents to consult, in one LLM call. Honors metadata.skillId
(skip LLM entirely) and metadata.focus_sources (override consult list)."""
from __future__ import annotations

import json
import logging
from typing import Iterable

from langchain_core.messages import HumanMessage

logger = logging.getLogger(__name__)


# Skill-level whitelist of mandatory peer consults. Unconditional — applied
# regardless of LLM output, because these skills semantically REQUIRE that
# grounding to give an answer worth giving (e.g. a workout recommendation
# without recovery context is irresponsible). User-supplied focus_sources
# still wins; this only fills in when the LLM would otherwise leave the
# consult list empty.
MANDATORY_CONSULTS: dict[str, list[str]] = {
    "get_workout_recommendations": ["recovery", "sleep"],
    "get_nutrition_recommendations": ["workout"],
    "analyze_mood": ["sleep"],
    "analyze_body_trend": ["nutrition", "workout"],
    "get_recommendations": ["sleep"],  # recovery agent's recommendations skill
    "get_sleep_recommendations": ["recovery"],
}


def _mandatory_consults_prompt_block() -> str:
    """Render MANDATORY_CONSULTS into the router-prompt format.

    Single source of truth — adding a new whitelist entry to the constant
    automatically updates the LLM router prompt as well.
    """
    if not MANDATORY_CONSULTS:
        return ""
    lines = [
        "MANDATORY CONSULTS (always added on top of your choice for these skills):"
    ]
    for skill, peers in MANDATORY_CONSULTS.items():
        lines.append(f"  {skill} -> {', '.join(peers)}")
    return "\n".join(lines) + "\n\n"


def _meta_get(metadata, key):
    if metadata is None:
        return None
    if isinstance(metadata, dict):
        return metadata.get(key)
    return getattr(metadata, key, None)


def _apply_mandatory_consults(
    skill_id: str | None,
    consult: list[str],
    candidate_peers: list[str],
) -> list[str]:
    """Inject any mandatory peers for this skill into consult, preserving order
    and deduplicating. Filtered to candidate_peers (defensive)."""
    mandated = MANDATORY_CONSULTS.get(skill_id or "", [])
    if not mandated:
        return consult
    out = list(consult)
    seen = set(out)
    for p in mandated:
        if p in candidate_peers and p not in seen:
            out.append(p)
            seen.add(p)
    return out


async def infer_skill_and_consults(
    *,
    message: str,
    skills: Iterable[str],
    candidate_peers: Iterable[str],
    metadata: dict | None,
    llm,
) -> tuple[str | None, list[str]]:
    """Decide which skill to run AND which peer agents to consult.

    Resolution order:
    1. metadata.skillId provided and valid → use it; consult = metadata.focus_sources or [].
    2. No metadata.skillId → one LLM call returns JSON {"skill": ..., "consult": [...]}.
       metadata.focus_sources, if provided, overrides the LLM's consult list.
       After resolving the consult list, mandatory consults for the skill are merged in.

    Both consult lists are filtered to candidate_peers (defensive: drops hallucinations
    or stale source names). Returns (None, []) if the LLM call fails or yields garbage —
    callers should fail the request with a clear status.
    """
    skills_list = list(skills)
    peers_list = list(candidate_peers)

    meta_skill = _meta_get(metadata, "skillId")
    meta_focus = _meta_get(metadata, "focus_sources")
    focus_override = (
        [p for p in meta_focus if p in peers_list]
        if isinstance(meta_focus, list)
        else None
    )

    if meta_skill in skills_list:
        # Explicit metadata.skillId means caller has already decided intent —
        # honor focus_sources verbatim when provided. Otherwise apply the
        # unconditional mandatory-consult whitelist so programmatic callers
        # (mobile chips, scheduled tools) receive the same grounding as
        # typed-message callers.
        if focus_override is not None:
            return meta_skill, focus_override
        return meta_skill, _apply_mandatory_consults(meta_skill, [], peers_list)

    prompt = (
        "You are a router. Output strict JSON only — no prose, no code fences.\n"
        "Schema: {\"skill\": <one of skills>, \"consult\": [<zero or more of peers>]}\n\n"
        f"Available skills: {', '.join(skills_list)}\n"
        f"Available peers: {', '.join(peers_list) or '(none)'}\n\n"
        "Pick the skill that matches the user's intent. Pick consult peers ONLY when "
        "the user explicitly references that domain (sleep, nutrition, recovery, etc.) "
        "or when the skill semantically requires it (e.g. workout recommendation that "
        "the user asked to ground in recovery state). When in doubt, prefer empty consult.\n\n"
        + _mandatory_consults_prompt_block()
        + f"User message: {message}"
    )
    try:
        result = await llm.ainvoke([HumanMessage(prompt)])
        raw = result.content if isinstance(result.content, str) else str(result.content)
    except Exception as e:
        logger.warning("intent LLM call failed: %s", e)
        return None, []

    try:
        parsed = json.loads(raw.strip())
    except (ValueError, AttributeError):
        logger.warning("intent LLM returned non-JSON: %r", raw[:200])
        return None, []

    skill_id = parsed.get("skill") if isinstance(parsed, dict) else None
    if skill_id not in skills_list:
        return None, []

    if focus_override is not None:
        return skill_id, focus_override

    consult_raw = parsed.get("consult") if isinstance(parsed, dict) else None
    consult = [p for p in (consult_raw or []) if p in peers_list]
    consult = _apply_mandatory_consults(skill_id, consult, peers_list)
    return skill_id, consult
