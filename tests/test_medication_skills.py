"""Tests for medication agent skill declarations."""
from agents.medication.app.skills import SKILLS, build_agent_card, SKILL_PROMPTS


def test_5_skills_declared():
    ids = [s.id for s in SKILLS]
    assert ids == [
        "define_medication", "log_taken", "list_active",
        "analyze_adherence", "archive_medication",
    ]


def test_card_includes_all_skills():
    card = build_agent_card()
    assert card.name == "medication-agent"
    assert len(card.skills) == 5
    assert card.protocol_version == "0.3.0"


def test_skill_prompts_keys_match_skills():
    assert set(SKILL_PROMPTS) == {s.id for s in SKILLS}
