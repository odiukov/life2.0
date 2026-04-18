"""Guards on _SYSTEM_PROMPT for recovery agent + workout→recovery chain."""
import sys
import types
from unittest.mock import AsyncMock

# copilotkit's __init__ tries to import langgraph.graph.graph which was removed
# in newer LangGraph versions.  Stub the module so health_agent can be imported
# in the test process without a running stack.
_ck = types.ModuleType("copilotkit")
_ck_lg = types.ModuleType("copilotkit.langgraph")
_ck_lg.copilotkit_emit_state = AsyncMock()
_ck.langgraph = _ck_lg
sys.modules.setdefault("copilotkit", _ck)
sys.modules.setdefault("copilotkit.langgraph", _ck_lg)


def test_system_prompt_mentions_seven_peer_agents():
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    lower = _SYSTEM_PROMPT.lower()
    assert "seven" in lower or "7" in _SYSTEM_PROMPT
    for agent in ("sleep", "workout", "nutrition", "body", "mood", "habits", "recovery"):
        assert agent in lower


def test_system_prompt_has_workout_recovery_chain_guidance():
    """For workout recommendations, ReAct must consult recovery first."""
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    lower = _SYSTEM_PROMPT.lower()
    assert "recovery" in lower
    assert "workout" in lower
    assert any(kw in lower for kw in (
        "first call ask_recovery_agent",
        "first call recovery",
        "check recovery first",
        "before asking workout",
        "before ask_workout_agent",
    ))


def test_ask_recovery_agent_tool_docstring_mentions_three_skills():
    from orchestrator.app.health_agent import ask_recovery_agent
    doc = (ask_recovery_agent.description or "").lower()
    assert "get_readiness" in doc
    assert "analyze_recovery_trend" in doc
    assert "get_recommendations" in doc


def test_system_prompt_preserves_habits_command_only_guard():
    """Previous guard (habits T12) must survive this edit."""
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    assert "/habit" in _SYSTEM_PROMPT
    assert "NOT" in _SYSTEM_PROMPT or "must not" in _SYSTEM_PROMPT.lower()


def test_system_prompt_preserves_calendar_destructive_ops_clause():
    """Previous guard (calendar T7) must survive this edit."""
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    lower = _SYSTEM_PROMPT.lower()
    destructive = sum(verb in lower for verb in ("create", "update", "delete"))
    assert destructive >= 2
    assert any(kw in lower for kw in ("confirm", "paraphrase", "ask before"))
