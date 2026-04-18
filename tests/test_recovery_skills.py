def test_recovery_skills_list():
    from agents.recovery.app.skills import SKILLS, SKILL_PROMPTS
    ids = {s.id for s in SKILLS}
    assert ids == {"get_readiness", "analyze_recovery_trend", "get_recommendations"}
    assert set(SKILL_PROMPTS.keys()) == ids


def test_recovery_agent_card_has_protocol_03():
    from agents.recovery.app.skills import build_agent_card
    card = build_agent_card()
    assert card.protocol_version == "0.3.0"
    assert card.name == "recovery-agent"
    assert len(card.skills) == 3


def test_recovery_skill_examples_present():
    from agents.recovery.app.skills import SKILLS
    for s in SKILLS:
        assert s.examples, f"skill {s.id} must have examples"
        assert s.description
