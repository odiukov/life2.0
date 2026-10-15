from shared.skill_ids import Dashboard, Feed, Workout
from workout.adapters.a2a.card import PEER_SKILLS, SKILLS, build_agent_card


def test_conversational_card_is_unchanged() -> None:
    card = build_agent_card("http://agent-workout:8002/")
    assert card.name == "workout-agent"
    assert [
        s.id for s in SKILLS if s.id not in {Dashboard.CARD, Dashboard.DETAIL, Feed.EVENTS}
    ] == [
        Workout.LOG,
        Workout.ANALYZE,
        Workout.RECOMMENDATIONS,
    ]
    assert PEER_SKILLS == {
        "recovery": "analyze_recovery_trend",
        "sleep": "analyze_sleep",
        "nutrition": "analyze_nutrition",
        "body": "analyze_body_trend",
        "habits": "analyze_habit",
        "medication": "analyze_adherence",
    }

    assert [
        s.name for s in SKILLS if s.id not in {Dashboard.CARD, Dashboard.DETAIL, Feed.EVENTS}
    ] == [
        "Log Workout",
        "Analyze Workout",
        "Workout Recommendations",
    ]
    assert [
        s.examples for s in SKILLS if s.id not in {Dashboard.CARD, Dashboard.DETAIL, Feed.EVENTS}
    ] == [
        ["Пробежал 5 км", "Did 3x5 squats at 100kg"],
        ["Как у меня с тренировками за неделю?"],
        None,
    ]
    assert card.description == "Tracks workouts, activities, training load"


def test_card_declares_structured_dashboard_skills() -> None:
    assert {s.id for s in SKILLS if "structured" in s.tags} == {
        Dashboard.CARD,
        Dashboard.DETAIL,
        Feed.EVENTS,
    }
