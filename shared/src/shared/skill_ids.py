"""Single source of truth for A2A peer skill IDs.

Two consumers import from this module:

1. Peer agents (`agents/*/app/skills.py`) — for `AgentSkill(id=...)` and
   `SKILL_PROMPTS` keys.
2. Orchestrator (`orchestrator.domain.catalog`) — for tool `Literal[...]` signatures.

Each agent has a class with `Final` string constants AND a corresponding
`Literal[...]` alias. mypy/Pylance do not narrow types through class
attributes, so tool signatures use the Literal form. Values stay in sync
because they are written once at module load.
"""

from __future__ import annotations

from typing import Final, Literal


class Sleep:
    LOG: Final = "log_sleep"
    ANALYZE: Final = "analyze_sleep"
    RECOMMENDATIONS: Final = "get_sleep_recommendations"


SleepSkillId = Literal["log_sleep", "analyze_sleep", "get_sleep_recommendations"]


class Workout:
    LOG: Final = "log_workout"
    ANALYZE: Final = "analyze_workout"
    RECOMMENDATIONS: Final = "get_workout_recommendations"


WorkoutSkillId = Literal["log_workout", "analyze_workout", "get_workout_recommendations"]


class Nutrition:
    LOG_MEAL: Final = "log_meal"
    ANALYZE: Final = "analyze_nutrition"
    RECOMMENDATIONS: Final = "get_nutrition_recommendations"
    SET_BODY_PROFILE: Final = "set_body_profile"


NutritionSkillId = Literal[
    "log_meal",
    "analyze_nutrition",
    "get_nutrition_recommendations",
    "set_body_profile",
]


class Body:
    IMPORT_VIHEALTH: Final = "body.import_vihealth"
    GET_LATEST: Final = "get_latest_body"
    ANALYZE_TREND: Final = "analyze_body_trend"


BodySkillId = Literal["get_latest_body", "analyze_body_trend"]


class Mood:
    LOG: Final = "log_mood"
    ANALYZE: Final = "analyze_mood"
    RECOMMENDATIONS: Final = "get_mood_recommendations"
    COACH_SESSION: Final = "coach_session"


MoodSkillId = Literal[
    "log_mood",
    "analyze_mood",
    "get_mood_recommendations",
    "coach_session",
]


class Habits:
    DEFINE: Final = "define_habit"
    LOG_CHECK: Final = "log_habit_check"
    ANALYZE: Final = "analyze_habit"
    STREAK_SUMMARY: Final = "get_streak_summary"
    ARCHIVE: Final = "archive_habit"


HabitsSkillId = Literal[
    "define_habit",
    "log_habit_check",
    "analyze_habit",
    "get_streak_summary",
    "archive_habit",
]


class Recovery:
    READINESS: Final = "get_readiness"
    ANALYZE_TREND: Final = "analyze_recovery_trend"
    RECOMMENDATIONS: Final = "get_recommendations"


RecoverySkillId = Literal["get_readiness", "analyze_recovery_trend", "get_recommendations"]


class Medication:
    DEFINE: Final = "define_medication"
    LOG: Final = "log_medication"
    LIST: Final = "list_active"
    ANALYZE: Final = "analyze_adherence"
    ARCHIVE: Final = "archive_medication"


MedicationSkillId = Literal[
    "define_medication",
    "log_medication",
    "list_active",
    "analyze_adherence",
    "archive_medication",
]


class Kitchen:
    UPDATE_INVENTORY: Final = "kitchen.update_inventory"
    QUERY: Final = "kitchen.query"
    INVENTORY: Final = "kitchen.inventory"
    DIGEST: Final = "kitchen.digest"
    ITEM_ACTION: Final = "kitchen.item_action"
    UNDO: Final = "kitchen.undo"


# Conversational skills only; the gateway calls structured skills directly.
KitchenSkillId = Literal["kitchen.update_inventory", "kitchen.query"]


class Dashboard:
    """Structured skills every health agent serves for the app's dashboard (no LLM)."""

    CARD: Final = "dashboard.card"
    DETAIL: Final = "dashboard.detail"


class Finance:
    ASK: Final = "finance.ask"
    IMPORT_STATEMENT: Final = "finance.import_statement"


FinanceSkillId = Literal["finance.ask"]


class Calendar:
    """Structured only: the calendar agent has no LLM."""

    CONNECT: Final = "calendar.connect"
    DISCONNECT: Final = "calendar.disconnect"
    STATUS: Final = "calendar.status"
    LIST: Final = "calendar.list"
    PROPOSE: Final = "calendar.propose_change"
    APPLY: Final = "calendar.apply_change"


class Home:
    CONNECT: Final = "home.connect"
    DISCONNECT: Final = "home.disconnect"
    STATUS: Final = "home.status"
    TEST: Final = "home.test"
    ASK: Final = "home.ask"
    APPLY: Final = "home.apply_action"


HomeSkillId = Literal["home.ask"]


class Feed:
    """Structured skill each personal agent serves for the app's day feed (no LLM)."""

    EVENTS: Final = "feed.events"
