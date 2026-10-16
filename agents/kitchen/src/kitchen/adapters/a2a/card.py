"""The kitchen agent card. Conversational skills are tagged so the orchestrator can tell them apart."""

from __future__ import annotations

from a2a.types import AgentCapabilities, AgentCard, AgentSkill
from shared.skill_ids import Attention, Kitchen

SKILLS: list[AgentSkill] = [
    AgentSkill(
        id=Kitchen.UPDATE_INVENTORY,
        name="Update kitchen inventory",
        description=(
            "Record food bought, eaten, opened, moved or thrown away from free text, "
            "or undo the person's last kitchen change. Asks one question when a reference is ambiguous."
        ),
        tags=["kitchen", "conversational"],
        examples=["bought two litres of milk and ten eggs", "finished the cheese", "undo"],
    ),
    AgentSkill(
        id=Kitchen.QUERY,
        name="Ask about food at home",
        description="Answer questions about what is in the fridge, freezer or pantry and what expires soon.",
        tags=["kitchen", "conversational"],
        examples=["what vegetables do we have?", "what expires soon?"],
    ),
    AgentSkill(
        id=Kitchen.INVENTORY,
        name="Inventory (structured)",
        description="Active batches as JSON.",
        tags=["kitchen", "structured"],
    ),
    AgentSkill(
        id=Kitchen.DIGEST,
        name="Expiry digest (structured)",
        description="Expired and expiring batches as JSON.",
        tags=["kitchen", "structured"],
    ),
    AgentSkill(
        id=Kitchen.ITEM_ACTION,
        name="Item action (structured)",
        description="Eat, discard, open, move, re-date or re-quantify one batch.",
        tags=["kitchen", "structured"],
    ),
    AgentSkill(
        id=Kitchen.UNDO,
        name="Undo (structured)",
        description="Undo one operation group.",
        tags=["kitchen", "structured"],
    ),
    AgentSkill(
        id=Attention.ITEMS,
        name="Attention items",
        description="Things in the kitchen that need doing today, for the app's Me screen.",
        tags=["structured"],
    ),
]


def build_agent_card(url: str) -> AgentCard:
    return AgentCard(
        protocol_version="0.3.0",
        name="kitchen-agent",
        description="Keeps the household's food inventory: purchases, consumption, expiry and a daily digest.",
        url=url,
        version="1.0.0",
        capabilities=AgentCapabilities(streaming=True, push_notifications=False),
        default_input_modes=["text"],
        default_output_modes=["text"],
        skills=SKILLS,
    )
