from habits.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card
from shared.skill_ids import Habits


def test_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-habits:8006/")
    assert card.name == "habits-agent"
    assert {s.id for s in SKILLS} == {
        Habits.DEFINE,
        Habits.LOG_CHECK,
        Habits.ANALYZE,
        Habits.STREAK_SUMMARY,
        Habits.ARCHIVE,
    }
    assert PEER_SKILLS == {
        "mood": "analyze_mood",
        "sleep": "analyze_sleep",
        "workout": "analyze_workout",
    }
