from shared.skill_ids import Sleep
from sleep.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card


def test_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-sleep:8001/")
    assert card.name == "sleep-agent"
    assert card.url == "http://agent-sleep:8001/"
    assert [s.id for s in SKILLS] == [Sleep.LOG, Sleep.ANALYZE, Sleep.RECOMMENDATIONS]
    assert PEER_SKILLS == {
        "workout": "analyze_workout",
        "nutrition": "analyze_nutrition",
        "recovery": "analyze_recovery_trend",
        "mood": "analyze_mood",
        "medication": "analyze_adherence",
    }
