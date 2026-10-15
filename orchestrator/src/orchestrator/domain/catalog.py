"""Every agent the chat can route to, and how. One entry per agent; tools are generated from it."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal, get_args

from shared.skill_ids import (
    BodySkillId,
    FinanceSkillId,
    HabitsSkillId,
    HomeSkillId,
    KitchenSkillId,
    MedicationSkillId,
    RecoverySkillId,
)
from shared.skill_ids import (
    MoodSkillId as MoodTool,
)
from shared.skill_ids import (
    NutritionSkillId as NutritionTool,
)
from shared.skill_ids import (
    SleepSkillId as SleepTool,
)
from shared.skill_ids import (
    WorkoutSkillId as WorkoutTool,
)


@dataclass(frozen=True, slots=True)
class CatalogEntry:
    name: str
    description: str
    skills: tuple[str, ...]
    accepts_focus_sources: tuple[str, ...] = ()
    proposes_actions: bool = False
    household_scoped: bool = False
    tool: Literal["ask", "calendar", "none"] = "ask"


def _entry(name: str, skills: object, description: str, **flags: object) -> CatalogEntry:
    return CatalogEntry(name=name, description=description, skills=tuple(get_args(skills)), **flags)  # type: ignore[arg-type]


CATALOG: dict[str, CatalogEntry] = {
    e.name: e
    for e in (
        _entry(
            "sleep",
            SleepTool,
            "Call sleep-agent. Use 'log_sleep' to record a new entry, 'analyze_sleep' to discuss quality/trends, 'get_sleep_recommendations' for actionable advice. Pass focus_sources=['workout','nutrition','recovery',...] when the user explicitly cites those domains as the basis for advice — otherwise omit and the agent uses minimal context.",
            accepts_focus_sources=("workout", "nutrition"),
        ),
        _entry(
            "workout",
            WorkoutTool,
            "Call workout-agent. Skills: log_workout / analyze_workout / get_workout_recommendations. Pass focus_sources=['sleep','nutrition','recovery',...] when the user explicitly cites those domains as the basis for advice — otherwise omit and the agent uses minimal context.",
            accepts_focus_sources=("sleep", "nutrition"),
        ),
        _entry(
            "nutrition",
            NutritionTool,
            "Call nutrition-agent. Skills: log_meal / analyze_nutrition / get_nutrition_recommendations / set_body_profile (save height, age, sex, activity_level, or calorie_goal_override so the agent can calculate an accurate daily calorie goal / TDEE). Pass focus_sources=['workout','sleep','recovery',...] when the user explicitly cites those domains as the basis for advice — otherwise omit and the agent uses minimal context.",
            accepts_focus_sources=("sleep", "workout"),
        ),
        _entry(
            "kitchen",
            KitchenSkillId,
            "Call kitchen-agent about the household's food at home (fridge, freezer, pantry). Skills: kitchen.update_inventory (food bought, eaten, opened, moved or thrown away, or the user asks to undo their last kitchen change) / kitchen.query (what is at home, what expires soon). Pass the user's words unchanged. Relay the kitchen reply to the user verbatim, including any question it asks. When the user answers a kitchen question, send that answer to ask_kitchen_agent with skill=kitchen.update_inventory.",
            household_scoped=True,
        ),
        _entry(
            "body",
            BodySkillId,
            "Call body-agent. Skills: get_latest_body (current weight/fat/muscle snapshot) or analyze_body_trend (dynamics with nutrition/workout correlation).",
        ),
        _entry(
            "mood",
            MoodTool,
            "Call mood-agent. Skills: log_mood (record a new mood entry from free-text or /mood), analyze_mood (trend over the last N days), get_mood_recommendations (short actionable advice), coach_session (record a completed coach session aggregate — usually driven by the chat coach loop, not by the orchestrator).",
        ),
        _entry(
            "habits",
            HabitsSkillId,
            "Call habits-agent. Skills: define_habit (create a new habit from '/habit new ...' free text), log_habit_check (record one check-in; user must use the /habit command — do NOT call this from free text), analyze_habit (adherence summary for a window, default 7 days), get_streak_summary (deterministic one-liner of current streaks per habit), archive_habit (soft-delete a habit).",
        ),
        _entry(
            "recovery",
            RecoverySkillId,
            "Call recovery-agent. Skills: get_readiness (today's bucket + HRV/RHR/stress/body-battery with deltas), analyze_recovery_trend (per-metric 7-day trend + correlations), get_recommendations (2–3 actionable recovery recommendations).",
        ),
        _entry(
            "medication",
            MedicationSkillId,
            "Call medication-agent. Skills: define_medication (parse free text into a structured medication and persist), log_medication (record one dose taken; resolves medication by name), list_active (deterministic list of currently tracked medications), analyze_adherence (LLM summary of adherence over a window, default 14 days), archive_medication (soft-delete a medication by name).",
        ),
        _entry(
            "finance",
            FinanceSkillId,
            "Call finance-agent about the user's money from their Payoneer statements: income, spending by category, balance and how long the money will last. Pass the user's question unchanged; currencies are never converted.",
        ),
        _entry(
            "home",
            HomeSkillId,
            "Call home-agent about the household's Home Assistant: the state of the house (temperature, lights, devices) and changes to it. Pass the user's words unchanged. A change comes back as a proposal that the user confirms in the app; relay the agent's reply.",
            proposes_actions=True,
            household_scoped=True,
        ),
        CatalogEntry(
            name="calendar",
            description="Google Calendar of the user.",
            skills=(),
            proposes_actions=True,
            tool="calendar",
        ),
    )
}
LEAD_AGENTS = frozenset(CATALOG)
_TOOL_TO_AGENT = {f"ask_{name}_agent": name for name, e in CATALOG.items() if e.tool == "ask"} | {
    "calendar_list": "calendar",
    "calendar_propose": "calendar",
}


def tool_name(agent: str) -> str:
    return f"ask_{agent}_agent"


def agent_for_tool(name: str) -> str | None:
    return _TOOL_TO_AGENT.get(name)
