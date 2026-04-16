import pytest


def test_body_skills_list():
    from agents.body.app.skills import SKILLS, SKILL_PROMPTS
    ids = {s.id for s in SKILLS}
    assert ids == {"get_latest_body", "analyze_body_trend"}
    assert set(SKILL_PROMPTS.keys()) == ids


def test_body_agent_card_has_protocol_03():
    from agents.body.app.skills import build_agent_card
    card = build_agent_card()
    assert card.protocol_version == "0.3.0"
    assert card.name == "body-agent"
    assert len(card.skills) == 2
