import pytest


def test_mood_skills_list():
    from agents.mood.app.skills import SKILLS, SKILL_PROMPTS
    ids = {s.id for s in SKILLS}
    assert ids == {"log_mood", "analyze_mood", "get_mood_recommendations", "coach_session"}
    assert set(SKILL_PROMPTS.keys()) == ids


def test_mood_agent_card_has_protocol_03():
    from agents.mood.app.skills import build_agent_card
    card = build_agent_card()
    assert card.protocol_version == "0.3.0"
    assert card.name == "mood-agent"
    assert len(card.skills) == 4


def test_mood_skill_examples_present():
    from agents.mood.app.skills import SKILLS
    for s in SKILLS:
        assert s.examples, f"skill {s.id} must have examples"
        assert s.description
