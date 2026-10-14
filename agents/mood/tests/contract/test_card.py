from mood.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from shared.skill_ids import Mood


def test_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-mood:8005/")
    assert card.name == "mood-agent"
    assert [s.id for s in SKILLS] == [
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
