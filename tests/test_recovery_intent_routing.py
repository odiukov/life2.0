"""Guards on _SYSTEM_PROMPT for recovery agent + workout→recovery chain."""


def test_system_prompt_mentions_eight_peer_agents():
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    lower = _SYSTEM_PROMPT.lower()
    assert "eight" in lower or "8" in _SYSTEM_PROMPT
    for agent in ("sleep", "workout", "nutrition", "body", "mood", "habits", "recovery", "medication"):
        assert agent in lower


def test_system_prompt_has_workout_recovery_chain_guidance():
    """Recovery escape hatch must survive: readiness questions should still
    route via ask_recovery_agent. Wording is descriptive (post-2026-04-28
    refactor), not imperative."""
    from orchestrator.app.health_agent import _SYSTEM_PROMPT
    lower = _SYSTEM_PROMPT.lower()
    # Both agents are still named in the prompt
    assert "recovery" in lower
    assert "workout" in lower
    # The new descriptive routing exposes focus_sources for cross-domain hints
    assert "focus_sources" in lower
    # Recovery escape hatch for readiness-language requests must remain
    assert any(kw in lower for kw in (
        "ask_recovery_agent first",
        "call ask_recovery_agent",
        "recovery state",
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
