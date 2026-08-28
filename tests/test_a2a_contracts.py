"""Cross-cutting A2A contract tests.

These tests assert that the three sources of truth for skill IDs do not
drift apart:
- `shared.skill_ids` — constants
- `agents.<name>.app.skills.SKILLS` + `SKILL_PROMPTS`
- `orchestrator.app.health_agent.ask_<name>_agent` Literal signatures

Adding a new skill must touch all three; these tests will catch a missed
spot at CI time."""
from __future__ import annotations

import importlib
import typing

import pytest


_AGENT_TO_CLASS = {
    "sleep": "Sleep",
    "workout": "Workout",
    "nutrition": "Nutrition",
    "body": "Body",
    "mood": "Mood",
    "habits": "Habits",
    "recovery": "Recovery",
    "medication": "Medication",
}


def _expected_ids_from_class(cls) -> set[str]:
    """Pull every str-valued class attribute that is not dunder."""
    return {
        v for k, v in vars(cls).items()
        if not k.startswith("_") and isinstance(v, str)
    }


@pytest.mark.parametrize("agent_name,class_name", list(_AGENT_TO_CLASS.items()))
def test_agent_card_skill_ids(agent_name, class_name):
    """AgentCard's SKILLS list matches the constants in shared.skill_ids."""
    skills_mod = importlib.import_module(f"agents.{agent_name}.app.skills")
    ids_mod = importlib.import_module("shared.skill_ids")

    cls = getattr(ids_mod, class_name)
    expected = _expected_ids_from_class(cls)
    declared = {s.id for s in skills_mod.SKILLS}

    assert expected <= declared, (
        f"{agent_name}: skill_ids declares {expected - declared} "
        f"that are missing from SKILLS"
    )


@pytest.mark.parametrize("agent_name", list(_AGENT_TO_CLASS))
def test_skill_prompts_match_skills(agent_name):
    """SKILL_PROMPTS keys (if present) cover every AgentSkill.id."""
    skills_mod = importlib.import_module(f"agents.{agent_name}.app.skills")
    if not hasattr(skills_mod, "SKILL_PROMPTS"):
        pytest.skip(f"{agent_name} has no SKILL_PROMPTS")

    prompt_keys = set(skills_mod.SKILL_PROMPTS)
    declared = {s.id for s in skills_mod.SKILLS}
    assert prompt_keys == declared, (
        f"{agent_name}: SKILL_PROMPTS={prompt_keys} != SKILLS={declared}"
    )


_TOOL_TO_AGENT = {
    "ask_sleep_agent": "sleep",
    "ask_workout_agent": "workout",
    "ask_nutrition_agent": "nutrition",
    "ask_body_agent": "body",
    "ask_mood_agent": "mood",
    "ask_habits_agent": "habits",
    "ask_recovery_agent": "recovery",
    "ask_medication_agent": "medication",
}


def _literal_args(tool_obj) -> set[str]:
    """Extract the strings inside Literal[...] for a tool's `skill` param.

    LangChain async StructuredTool stores the underlying coroutine in
    `.coroutine`; sync tools use `.func`. Fall back to the object itself
    if neither attr is set.
    """
    underlying = (
        getattr(tool_obj, "coroutine", None)
        or getattr(tool_obj, "func", None)
        or tool_obj
    )
    hints = typing.get_type_hints(underlying)
    return set(typing.get_args(hints["skill"]))


@pytest.mark.parametrize("tool_name,agent_name", list(_TOOL_TO_AGENT.items()))
def test_orchestrator_tool_literal_matches_skills(tool_name, agent_name):
    """Each ask_<peer>_agent's Literal[...] for `skill` matches the peer's
    declared SKILLS.
    """
    from orchestrator.app import health_agent
    skills_mod = importlib.import_module(f"agents.{agent_name}.app.skills")

    tool = getattr(health_agent, tool_name)
    declared = {s.id for s in skills_mod.SKILLS}
    allowed = _literal_args(tool)
    assert allowed == declared, (
        f"{tool_name}: Literal={allowed} != SKILLS({agent_name})={declared}"
    )
