"""Body agent skill declarations + per-skill prompt builders."""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Body, Dashboard, Feed

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Feed.EVENTS,
        name="Feed events",
        description="Events and insights of a day for the app's feed.",
        tags=["structured"],
    ),
    AgentSkill(
        id=Dashboard.CARD,
        name="Dashboard Card",
        description="Structured dashboard card.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Body.GET_LATEST,
        name="Get Latest Body Composition",
        description="Return the most recent weight, body fat %, muscle and related metrics.",
        tags=["body", "weight", "query"],
        examples=["сколько я вешу", "what's my weight", "current body fat"],
    ),
    AgentSkill(
        id=Body.ANALYZE_TREND,
        name="Analyze Body Trend",
        description="Analyze weight / fat / muscle dynamics and correlate with nutrition and training.",
        tags=["body", "analysis"],
        examples=["проанализируй историю веса", "how has my body composition changed"],
    ),
    AgentSkill(
        id=Body.IMPORT_VIHEALTH,
        name="Import ViHealth Report",
        description="Import a ViHealth body composition PDF.",
        tags=["body", "import", "structured"],
        input_modes=["application/pdf"],
    ),
]


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="body-agent",
        description=(
            "Owns body-composition data (weight, fat %, muscle, BMR, visceral fat, body age) "
            "ingested from ViHealth/LePulse scales. Answers current-state queries and trend analyses."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PEER_SKILLS: dict[str, str] = {
    "nutrition": "analyze_nutrition",
    "workout": "analyze_workout",
    "recovery": "analyze_recovery_trend",
}
