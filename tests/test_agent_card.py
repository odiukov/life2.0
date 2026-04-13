from agents.sleep.app.agent_card import AGENT_CARD
from agents.workout.app.agent_card import AGENT_CARD as WORKOUT_CARD
from agents.nutrition.app.agent_card import AGENT_CARD as NUTRITION_CARD


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


def test_nutrition_agent_card_has_required_fields():
    assert "name" in NUTRITION_CARD
    assert "description" in NUTRITION_CARD
    assert "url" in NUTRITION_CARD
    assert "capabilities" in NUTRITION_CARD
    assert "version" in NUTRITION_CARD


def test_nutrition_agent_card_capabilities():
    caps = NUTRITION_CARD["capabilities"]
    assert "log_meal" in caps
    assert "analyze_nutrition" in caps
    assert "get_recommendations" in caps
