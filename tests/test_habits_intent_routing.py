"""Verify LangGraph routes habit-command messages through log_habit_check but
NOT free-text habit mentions."""
import sys
import types
from unittest.mock import AsyncMock, MagicMock, patch

# copilotkit's __init__ tries to import langgraph.graph.graph which was removed
# in newer LangGraph versions.  Stub the module so health_agent can be imported
# in the test process without a running stack.
_ck = types.ModuleType("copilotkit")
_ck_lg = types.ModuleType("copilotkit.langgraph")
_ck_lg.copilotkit_emit_state = AsyncMock()
_ck.langgraph = _ck_lg
sys.modules.setdefault("copilotkit", _ck)
sys.modules.setdefault("copilotkit.langgraph", _ck_lg)

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
