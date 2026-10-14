from recovery.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from shared.skill_ids import Recovery


def test_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-recovery:8007/")
    assert card.name == "recovery-agent"
    assert card.protocol_version == "0.3.0"
    assert card.skills == SKILLS
    for skill in SKILLS:
        assert skill.examples
        assert skill.description
    assert [s.id for s in SKILLS] == [
        Recovery.READINESS,
        Recovery.ANALYZE_TREND,
        Recovery.RECOMMENDATIONS,
    ]
    assert [s.id for s in SKILLS] == [
        "get_readiness",
        "analyze_recovery_trend",
        "get_recommendations",
    ]
    assert PEER_SKILLS == {
        "sleep": "analyze_sleep",
        "workout": "analyze_workout",
        "nutrition": "analyze_nutrition",
        "mood": "analyze_mood",
    }
