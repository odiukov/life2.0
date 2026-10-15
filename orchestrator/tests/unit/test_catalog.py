from typing import get_args

from orchestrator.domain.catalog import CATALOG, LEAD_AGENTS, agent_for_tool, tool_name
from shared.schema.tables import CHAT_AGENTS
from shared.skill_ids import FinanceSkillId, HomeSkillId, KitchenSkillId


def test_every_chat_agent_is_in_the_catalog_and_can_lead() -> None:
    assert set(CATALOG) == set(CHAT_AGENTS) == set(LEAD_AGENTS)


def test_tools_round_trip() -> None:
    for name, entry in CATALOG.items():
        if entry.tool == "ask":
            assert agent_for_tool(tool_name(name)) == name
    assert agent_for_tool("calendar_propose") == "calendar"


def test_conversational_skills_only() -> None:
    assert CATALOG["kitchen"].skills == get_args(KitchenSkillId)
    assert CATALOG["finance"].skills == get_args(FinanceSkillId)
    assert CATALOG["home"].skills == get_args(HomeSkillId)
    assert all("dashboard." not in skill for e in CATALOG.values() for skill in e.skills)


def test_flags() -> None:
    assert {n for n, e in CATALOG.items() if e.proposes_actions} == {"calendar", "home"}
    assert {n for n, e in CATALOG.items() if e.household_scoped} == {"kitchen", "home"}
    assert CATALOG["sleep"].accepts_focus_sources == ("workout", "nutrition")
    assert CATALOG["mood"].accepts_focus_sources == ()
