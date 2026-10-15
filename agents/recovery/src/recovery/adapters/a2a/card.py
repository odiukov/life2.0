from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Dashboard, Feed, Recovery

SKILLS: list[AgentSkill] = [
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
        id=Recovery.READINESS,
        name="Get Today's Readiness",
        description=(
            "Return today's recovery snapshot: coarse bucket (recovered / neutral "
            "/ depleted / unknown) + HRV, RHR, stress, body-battery with trend "
            "deltas. Bucket rule is deterministic (shared.recovery.compute_bucket); "
            "LLM formats the human-readable response on top."
        ),
        tags=["recovery", "readiness", "query"],
        examples=[
            "как я восстанавливаюсь",
            "am I recovered today",
            "readiness",
        ],
    ),
    AgentSkill(
        id=Recovery.ANALYZE_TREND,
        name="Analyze Recovery Trend",
        description=(
            "Analyze recovery metrics over a window (default 7 days): per-metric "
            "trend direction, outlier days, correlations between HRV / stress / RHR."
        ),
        tags=["recovery", "analysis"],
        examples=[
            "recovery trend this week",
            "как менялся мой HRV за неделю",
        ],
    ),
    AgentSkill(
        id=Recovery.RECOMMENDATIONS,
        name="Get Recovery Recommendations",
        description=(
            "2–3 actionable recommendations based on last 7 days of recovery data. "
            "Tone is practical, not prescriptive."
        ),
        tags=["recovery", "recommendations"],
        examples=[
            "what should I do to recover better",
            "посоветуй что делать если HRV просел",
        ],
    ),
]


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="recovery-agent",
        description=(
            "Read-only analytical lens over Garmin-synced recovery metrics "
            "(HRV, RHR, stress, body battery). Produces bucket (recovered / "
            "neutral / depleted / unknown), trend analysis, and recommendations."
        ),
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )


PEER_SKILLS: dict[str, str] = {
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
    "mood": "analyze_mood",
}
