from kitchen.adapters.a2a.card import build_agent_card
from shared.skill_ids import Kitchen


def test_card_lists_all_skills_and_is_discoverable_as_kitchen() -> None:
    card = build_agent_card("http://agent-kitchen:8009/")
    assert card.name == "kitchen-agent"  # the orchestrator registry strips "-agent"
    assert {s.id for s in card.skills} == {
        Kitchen.UPDATE_INVENTORY,
        Kitchen.QUERY,
        Kitchen.INVENTORY,
        Kitchen.DIGEST,
        Kitchen.ITEM_ACTION,
        Kitchen.UNDO,
    }
    conversational = [s for s in card.skills if "conversational" in (s.tags or [])]
    assert {s.id for s in conversational} == {Kitchen.UPDATE_INVENTORY, Kitchen.QUERY}
