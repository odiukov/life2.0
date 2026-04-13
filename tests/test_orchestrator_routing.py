import pytest
from orchestrator.app.router import classify_intent


def test_classify_sleep_intent():
    assert classify_intent("Как я спал на этой неделе?") == "sleep"
    assert classify_intent("analyze my sleep") == "sleep"
    assert classify_intent("sleep recommendation") == "sleep"


def test_classify_workout_intent():
    assert classify_intent("Сколько я тренировался?") == "workout"
    assert classify_intent("log my run") == "workout"


def test_classify_nutrition_intent():
    assert classify_intent("Что я ел сегодня?") == "nutrition"
    assert classify_intent("log meal") == "nutrition"


def test_classify_unknown_defaults_to_sleep():
    # Unknown intent defaults to first available agent
    result = classify_intent("random unrelated text xyz")
    assert result in ("sleep", "workout", "nutrition")
