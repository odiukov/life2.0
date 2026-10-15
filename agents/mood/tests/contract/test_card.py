from mood.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from shared.skill_ids import Dashboard, Feed, Mood


def test_conversational_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-mood:8005/")
    assert card.name == "mood-agent"
    assert [
        s.id for s in SKILLS if s.id not in {Dashboard.CARD, Dashboard.DETAIL, Feed.EVENTS}
    ] == [
        Mood.LOG,
        Mood.ANALYZE,
        Mood.RECOMMENDATIONS,
        Mood.COACH_SESSION,
    ]
    assert PEER_SKILLS == {
        "sleep": "analyze_sleep",
        "recovery": "analyze_recovery_trend",
        "workout": "analyze_workout",
        "habits": "analyze_habit",
        "medication": "analyze_adherence",
    }


def test_card_declares_structured_dashboard_skills() -> None:
    assert {s.id for s in SKILLS if "structured" in s.tags} == {
        Dashboard.CARD,
        Dashboard.DETAIL,
        Feed.EVENTS,
    }
