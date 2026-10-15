"""The unchanged legacy nutrition agent card, including its Russian examples."""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Dashboard, Nutrition

from nutrition.application.peers import PEER_SKILLS

__all__ = ["PEER_SKILLS", "SKILLS", "build_agent_card"]

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Dashboard.CARD,
        name="Dashboard Card",
        description="Structured dashboard tile, featured block and rings.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Dashboard.DETAIL,
        name="Dashboard Detail",
        description="Structured dashboard metrics and history.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Nutrition.LOG_MEAL,
        name="Log Meal",
        description="Log a meal from free text and estimate macros (kcal, protein, carbs, fat).",
        tags=["nutrition", "logging"],
        examples=["Съел омлет из 3 яиц и тост", "Had chicken salad for lunch"],
    ),
    AgentSkill(
        id=Nutrition.ANALYZE,
        name="Analyze Nutrition",
        description="Analyze nutrition patterns, macro trends, and meal timing.",
        tags=["nutrition", "analysis"],
        examples=["Как у меня с питанием за неделю?"],
    ),
    AgentSkill(
        id=Nutrition.RECOMMENDATIONS,
        name="Nutrition Recommendations",
        description="Give actionable nutrition recommendations based on recent workouts and macros.",
        tags=["nutrition", "advice"],
    ),
    AgentSkill(
        id=Nutrition.SET_BODY_PROFILE,
        name="Set Body Profile",
        description=(
            "Save the user's body profile (height, age, sex, activity level, calorie goal override) "
            "used to calculate their daily TDEE calorie goal."
        ),
        tags=["nutrition", "profile"],
        examples=[
            "I'm 180cm tall, 30 years old, male, moderately active",
            "My height is 165cm and I'm lightly active",
        ],
    ),
]


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="nutrition-agent",
        description=(
            "Logs meals from free text, parses macros with Claude, analyzes nutrition "
            "patterns, and gives recommendations tailored to recent workout load."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )
