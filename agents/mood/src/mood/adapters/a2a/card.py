from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Mood

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Mood.LOG,
        name="Log Mood Entry",
        description=(
            "Parse a free-text or explicit '/mood ...' message and record one mood "
            "entry with mood_score, energy, stress, valence, tags, and the raw text."
        ),
        tags=["mood", "journal", "log"],
        examples=[
            "чувствую себя паршиво, голова кипит",
            "/mood 6 устал но продуктивный день",
            "mood good, energetic, focused",
        ],
    ),
    AgentSkill(
        id=Mood.ANALYZE,
        name="Analyze Mood Trend",
        description=(
            "Summarize mood trends over a window (default 7 days): per-day averages, "
            "valence distribution, top tags, comparison with baseline."
        ),
        tags=["mood", "analysis"],
        examples=[
            "какое у меня настроение в этом неделю",
            "analyze my mood this week",
        ],
    ),
    AgentSkill(
        id=Mood.RECOMMENDATIONS,
        name="Get Mood Recommendations",
        description=(
            "Return short actionable advice based on the last 7 days of mood + valence "
            "+ tags. No structured fields."
        ),
        tags=["mood", "recommendations"],
        examples=[
            "что мне делать чтобы чувствовать себя лучше",
            "any mood advice",
        ],
    ),
    AgentSkill(
        id=Mood.COACH_SESSION,
        name="Coach Session Summary",
        description=(
            "Accept a completed coach session transcript and write a single aggregated "
            "mood entry with source_skill='coach_session'. Invoked by the chat coach "
            "loop on session finalization."
        ),
        tags=["mood", "coach"],
        examples=["finalize coach session"],
    ),
]


PEER_SKILLS: dict[str, str] = {
    "sleep": "analyze_sleep",
    "recovery": "analyze_recovery_trend",
    "workout": "analyze_workout",
    "habits": "analyze_habit",
    "medication": "analyze_adherence",
}


LEGACY_DESCRIPTION = (
    "Owns mood / journal data: mood scores, energy, stress, tags, free-text "
    "entries, and bounded coach sessions. Provides cross-agent context via "
    "shared vector memory."
)


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="mood-agent",
        description=LEGACY_DESCRIPTION,
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )
