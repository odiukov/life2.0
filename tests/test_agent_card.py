from agents.sleep.app.agent_card import AGENT_CARD


def test_agent_card_has_required_fields():
    assert "name" in AGENT_CARD
    assert "description" in AGENT_CARD
    assert "url" in AGENT_CARD
    assert "capabilities" in AGENT_CARD
    assert "version" in AGENT_CARD


def test_agent_card_capabilities():
    caps = AGENT_CARD["capabilities"]
    assert "analyze_sleep" in caps
    assert "log_sleep" in caps
    assert "get_recommendations" in caps
