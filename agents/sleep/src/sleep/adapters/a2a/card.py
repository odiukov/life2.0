"""Sleep agent A2A card and peer contracts."""

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Attention, Dashboard, Feed, Sleep

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Attention.ITEMS,
        name="Attention items",
        description="Things that need doing today, for the app's Me screen.",
        tags=["structured"],
    ),
    AgentSkill(
        id=Feed.EVENTS,
        name="Feed events",
        description="Events and insights of a day for the app's feed.",
        tags=["structured"],
    ),
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
        id=Sleep.LOG,
        name="Log Sleep",
        description="Log a new sleep entry from the user's message.",
        tags=["sleep", "logging"],
        examples=["Спал 7 часов", "Slept 6h30m, woke up tired"],
    ),
    AgentSkill(
        id=Sleep.ANALYZE,
        name="Analyze Sleep",
        description="Analyze sleep quality, duration, and recovery trends.",
        tags=["sleep", "analysis"],
        examples=["Как у меня со сном за неделю?"],
    ),
    AgentSkill(
        id=Sleep.RECOMMENDATIONS,
        name="Sleep Recommendations",
        description="Give actionable sleep-improvement recommendations based on history.",
        tags=["sleep", "advice"],
    ),
]


PEER_SKILLS: dict[str, str] = {
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
    "recovery": "analyze_recovery_trend",
    "mood": "analyze_mood",
    "medication": "analyze_adherence",
}


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="sleep-agent",
        description="Tracks sleep patterns, analyzes quality, and gives recommendations.",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )
