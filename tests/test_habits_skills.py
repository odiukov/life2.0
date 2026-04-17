def test_habits_skills_list():
    from agents.habits.app.skills import SKILLS, SKILL_PROMPTS
    ids = {s.id for s in SKILLS}
    assert ids == {
        "define_habit", "log_habit_check", "analyze_habit",
        "get_streak_summary", "archive_habit",
    }
    assert set(SKILL_PROMPTS.keys()) == ids


def test_habits_agent_card_has_protocol_03():
    from agents.habits.app.skills import build_agent_card
    card = build_agent_card()
    assert card.protocol_version == "0.3.0"
    assert card.name == "habits-agent"
    assert len(card.skills) == 5


def test_habits_skill_examples_present():
    from agents.habits.app.skills import SKILLS
    for s in SKILLS:
        assert s.examples, f"skill {s.id} must have examples"
        assert s.description
