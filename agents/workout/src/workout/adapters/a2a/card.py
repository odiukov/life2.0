from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Workout

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Workout.LOG,
        name="Log Workout",
        description="Log a new workout or training activity from the user's message.",
        tags=["workout", "logging"],
        examples=["Пробежал 5 км", "Did 3x5 squats at 100kg"],
    ),
    AgentSkill(
        id=Workout.ANALYZE,
        name="Analyze Workout",
        description="Analyze training volume, intensity, and recovery trends.",
        tags=["workout", "analysis"],
        examples=["Как у меня с тренировками за неделю?"],
    ),
    AgentSkill(
        id=Workout.RECOMMENDATIONS,
        name="Workout Recommendations",
        description="Give actionable training recommendations based on history and recovery.",
        tags=["workout", "advice"],
    ),
]


PEER_SKILLS: dict[str, str] = {
    "recovery": "analyze_recovery_trend",
    "sleep": "analyze_sleep",
    "nutrition": "analyze_nutrition",
    "body": "analyze_body_trend",
    "habits": "analyze_habit",
    "medication": "analyze_adherence",
}


LEGACY_DESCRIPTION = "Tracks workouts, activities, training load"


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="workout-agent",
        description=LEGACY_DESCRIPTION,
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )
