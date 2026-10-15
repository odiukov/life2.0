from recovery.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from shared.skill_ids import Dashboard, Feed, Recovery


def test_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-recovery:8007/")
    legacy = [s for s in SKILLS if s.id not in {Dashboard.CARD, Dashboard.DETAIL, Feed.EVENTS}]
    assert card.name == "recovery-agent"
    assert card.protocol_version == "0.3.0"
    assert card.skills == SKILLS
    for skill in legacy:
        assert skill.examples
        assert skill.description
    assert [s.id for s in legacy] == [
        Recovery.READINESS,
        Recovery.ANALYZE_TREND,
        Recovery.RECOMMENDATIONS,
    ]
    assert [s.id for s in legacy] == [
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


def test_card_declares_dashboard_skills() -> None:
    assert {s.id for s in SKILLS if "dashboard" in s.tags} == {Dashboard.CARD, Dashboard.DETAIL}


def test_card_declares_feed_skill() -> None:
    assert Feed.EVENTS in {s.id for s in SKILLS}
