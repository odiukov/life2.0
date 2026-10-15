from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Dashboard, Finance

SKILLS = [
    AgentSkill(
        id=Dashboard.DETAIL,
        name="Dashboard Detail",
        description="Structured dashboard detail.",
        tags=["dashboard", "structured"],
    ),
    AgentSkill(
        id=Finance.ASK,
        name="Answer Finance Questions",
        description="Income, spending by category, balance and runway from the user's statements.",
        tags=["finance", "analysis"],
        examples=["how much did I spend in October", "how many days will my money last"],
    ),
    AgentSkill(
        id=Finance.IMPORT_STATEMENT,
        name="Import Payoneer Statement",
        description="Structured: one Payoneer statement PDF as an attachment; stores and categorizes it.",
        tags=["finance", "import", "structured"],
    ),
]


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="finance-agent",
        description="Owns the user's transactions imported from Payoneer statements and answers money questions.",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text", "application/pdf"],
        default_output_modes=["text"],
        skills=SKILLS,
    )
