"""Verify LangGraph routes habit-command messages through log_habit_check but
NOT free-text habit mentions."""

import pytest


@pytest.mark.asyncio
async def test_habit_command_routes_to_log_habit_check():
    """When the user message is '/habit meditation', ask_habits_agent must be
    invoked with skill=log_habit_check."""
    from orchestrator.app.health_agent import ask_habits_agent
    doc = ask_habits_agent.description or ""
    assert "log_habit_check" in doc
    assert "/habit" in doc
    assert "do NOT" in doc or "not from free text" in doc.lower() or "not call this" in doc.lower()


@pytest.mark.asyncio
async def test_system_prompt_instructs_command_only_for_habits():
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    assert "/habit" in _SYSTEM_PROMPT
    assert "NOT" in _SYSTEM_PROMPT or "must not" in _SYSTEM_PROMPT.lower()
