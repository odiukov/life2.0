from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Attention, Dashboard, Feed, Habits

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Attention.ITEMS,
        name="Attention items",
        description="Things that need doing today, for the app's Me screen.",
        tags=["structured"],
    ),
    AgentSkill(
        id=Feed.EVENTS,
        name="Day Feed",
        description="Structured events of a local day.",
        tags=["feed", "structured"],
    ),
    AgentSkill(
        id=Dashboard.CARD,
        name="Dashboard Card",
        description="Structured dashboard card.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Dashboard.DETAIL,
        name="Dashboard Detail",
        description="Structured dashboard detail.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Habits.DEFINE,
        name="Define Habit",
        description=(
            "Parse free text (from '/habit new ...') into a structured habit definition "
            "with name (lowercase kebab-case), kind (boolean|quantitative), cadence "
            "(daily or specific weekdays), optional target_value + unit. Inserts a row "
            "in the habits table."
        ),
        tags=["habits", "define"],
        examples=[
            "медитация 20 минут каждый день",
            "cold shower every morning",
            "зал по пн/ср/пт",
        ],
    ),
    AgentSkill(
        id=Habits.LOG_CHECK,
        name="Log Habit Check-in",
        description=(
            "Record one check-in for an existing habit. Accepts either {habit_id} "
            "(from inline-button callback) or {name} (resolved via registry with "
            "name normalization). Optional value/unit/note."
        ),
        tags=["habits", "log"],
        examples=[
            "/habit meditation",
            "/habit meditation 15min",
            "mark cold-shower done",
        ],
    ),
    AgentSkill(
        id=Habits.ANALYZE,
        name="Analyze Habit Adherence",
        description=(
            "Summarize adherence over a window (default 7 days): % completion, "
            "current streak, longest streak, missed days, value distribution for "
            "quantitative habits. Aggregations in SQL, final text via LLM."
        ),
        tags=["habits", "analysis"],
        examples=[
            "how am I doing on my habits this week",
            "meditation streak",
        ],
    ),
    AgentSkill(
        id=Habits.STREAK_SUMMARY,
        name="Get Streak Summary",
        description=(
            "Deterministic one-liner across all active habits showing current streaks "
            "and (for quantitative) today's progress vs target. Used by /habits."
        ),
        tags=["habits", "summary"],
        examples=["streak summary", "/habits"],
    ),
    AgentSkill(
        id=Habits.ARCHIVE,
        name="Archive Habit",
        description=(
            "Soft-delete a habit (set archived_at). History in health_logs is preserved "
            "via the denormalized `name` field."
        ),
        tags=["habits", "archive"],
        examples=["/habit stop meditation", "stop tracking cold-shower"],
    ),
]


PEER_SKILLS: dict[str, str] = {
    "mood": "analyze_mood",
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
}

LEGACY_DESCRIPTION = "Owns habit definitions and daily check-ins: creates habits, logs completions (boolean or quantitative), and calculates streaks."


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="habits-agent",
        description=LEGACY_DESCRIPTION,
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )
