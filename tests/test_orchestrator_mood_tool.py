import pytest


def test_mood_tool_registered_in_graph():
    from orchestrator.app.health_agent import (
        ask_mood_agent,
        ask_sleep_agent,
        ask_workout_agent,
        ask_nutrition_agent,
        ask_body_agent,
    )
    # All five peer-agent tools must be importable and distinct.
    tools = [ask_sleep_agent, ask_workout_agent, ask_nutrition_agent, ask_body_agent, ask_mood_agent]
    names = {t.name for t in tools}
    assert len(names) == 5
    assert "ask_mood_agent" in names


def test_ask_mood_agent_accepts_all_four_skills():
    import typing
    from orchestrator.app.health_agent import ask_mood_agent

    # The @tool decorator wraps the coroutine; the literal is on the original fn.
    fn = ask_mood_agent.coroutine if hasattr(ask_mood_agent, "coroutine") else ask_mood_agent
    hints = typing.get_type_hints(fn)
    skill_literal = hints["skill"]
    allowed = set(typing.get_args(skill_literal))
    assert allowed == {"log_mood", "analyze_mood", "get_recommendations", "coach_session"}
