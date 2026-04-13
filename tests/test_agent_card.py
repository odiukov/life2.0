# tests/test_agent_card.py
from agents.sleep.app.agent_card import AGENT_CARD
from agents.workout.app.agent_card import AGENT_CARD as WORKOUT_CARD
from agents.nutrition.app.agent_card import AGENT_CARD as NUTRITION_CARD


def test_agent_card_has_required_fields():
    for card in (AGENT_CARD, WORKOUT_CARD, NUTRITION_CARD):
        assert "name" in card
        assert "description" in card
        assert "url" in card
        assert "capabilities" in card
        assert "version" in card
        assert "skills" in card


def test_agent_card_capabilities_a2a():
    for card in (AGENT_CARD, WORKOUT_CARD, NUTRITION_CARD):
        caps = card["capabilities"]
        assert caps["streaming"] is True
        assert caps["pushNotifications"] is True


def test_sleep_agent_card_skills():
    skill_ids = [s["id"] for s in AGENT_CARD["skills"]]
    assert "analyze_sleep" in skill_ids
    assert "log_sleep" in skill_ids
    assert "get_recommendations" in skill_ids


def test_workout_agent_card_skills():
    skill_ids = [s["id"] for s in WORKOUT_CARD["skills"]]
    assert "log_workout" in skill_ids
    assert "analyze_workout" in skill_ids
    assert "get_recommendations" in skill_ids


def test_nutrition_agent_card_skills():
    skill_ids = [s["id"] for s in NUTRITION_CARD["skills"]]
    assert "log_meal" in skill_ids
    assert "analyze_nutrition" in skill_ids
    assert "get_recommendations" in skill_ids
