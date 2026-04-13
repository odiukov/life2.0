from agents.sleep.app.agent_card import AGENT_CARD
from agents.workout.app.agent_card import AGENT_CARD as WORKOUT_CARD


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


def test_workout_agent_card_has_required_fields():
    assert "name" in WORKOUT_CARD
    assert "description" in WORKOUT_CARD
    assert "url" in WORKOUT_CARD
    assert "capabilities" in WORKOUT_CARD
    assert "version" in WORKOUT_CARD


def test_workout_agent_card_capabilities():
    caps = WORKOUT_CARD["capabilities"]
    assert "log_workout" in caps
    assert "analyze_workout" in caps
    assert "get_recommendations" in caps
