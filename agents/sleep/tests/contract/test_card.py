from shared.skill_ids import Attention, Dashboard, Feed, Sleep
from sleep.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card


def test_conversational_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-sleep:8001/")
    assert card.name == "sleep-agent"
    assert card.url == "http://agent-sleep:8001/"
    assert [
        s.id
        for s in SKILLS
        if s.id not in {Dashboard.CARD, Dashboard.DETAIL, Feed.EVENTS, Attention.ITEMS}
    ] == [
        Sleep.LOG,
        Sleep.ANALYZE,
        Sleep.RECOMMENDATIONS,
    ]
    assert PEER_SKILLS == {
        "workout": "analyze_workout",
        "nutrition": "analyze_nutrition",
        "recovery": "analyze_recovery_trend",
        "mood": "analyze_mood",
        "medication": "analyze_adherence",
    }


def test_card_declares_structured_dashboard_skills() -> None:
    assert {s.id for s in SKILLS if "structured" in s.tags} == {
        Dashboard.CARD,
        Dashboard.DETAIL,
        Feed.EVENTS,
        Attention.ITEMS,
    }
