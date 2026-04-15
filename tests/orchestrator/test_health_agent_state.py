"""A2A tools emit intermediate state and return Command(update=...) with
toolCalls transitions + lastLoggedEntry on log_* skills."""
from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from langchain_core.messages import ToolMessage
from langgraph.types import Command


class _FakeRunnableConfig(dict):
    """Minimal RunnableConfig stand-in."""


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent.copilotkit_emit_state", new_callable=AsyncMock)
@patch(
    "orchestrator.app.health_agent._call_agent_with_artifact",
    new=AsyncMock(return_value=(
        "Logged: 30 min run",
        {"summary": "30 min run", "timestamp": "2026-04-15T10:00:00+00:00"},
    )),
)
async def test_ask_workout_log_emits_running_then_returns_done_with_log_entry(emit_mock):
    from orchestrator.app.health_agent import ask_workout_agent

    state = {"messages": [], "toolCalls": []}
    cmd = await ask_workout_agent.ainvoke(
        {
            "name": "ask_workout_agent",
            "type": "tool_call",
            "id": "tc1",
            "args": {
                "message": "30 min run",
                "skill": "log_workout",
                "state": state,
            },
        },
        config=_FakeRunnableConfig(),
    )

    assert emit_mock.await_count == 1
    emitted_state = emit_mock.await_args.args[1]
    assert emitted_state["currentStep"] == "querying workout (log_workout)"
    assert emitted_state["activeAgent"] == "workout"
    assert len(emitted_state["toolCalls"]) == 1
    assert emitted_state["toolCalls"][0]["status"] == "running"
    assert emitted_state["toolCalls"][0]["id"] == "tc1"

    assert isinstance(cmd, Command)
    upd = cmd.update
    assert upd["activeAgent"] is None
    assert upd["currentStep"] == "composing"
    assert upd["toolCalls"][0]["status"] == "done"
    assert upd["lastLoggedEntry"] == {
        "agent": "workout",
        "skill": "log_workout",
        "summary": "30 min run",
        "timestamp": "2026-04-15T10:00:00+00:00",
    }
    assert isinstance(upd["messages"][0], ToolMessage)
    assert upd["messages"][0].tool_call_id == "tc1"


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent.copilotkit_emit_state", new_callable=AsyncMock)
@patch(
    "orchestrator.app.health_agent._call_agent_with_artifact",
    new=AsyncMock(return_value=("analysis text", None)),
)
async def test_ask_sleep_analyze_does_not_set_last_logged_entry(emit_mock):
    from orchestrator.app.health_agent import ask_sleep_agent

    state = {"messages": [], "toolCalls": []}
    cmd = await ask_sleep_agent.ainvoke(
        {
            "name": "ask_sleep_agent",
            "type": "tool_call",
            "id": "tc2",
            "args": {
                "message": "how did I sleep?",
                "skill": "analyze_sleep",
                "state": state,
            },
        },
        config=_FakeRunnableConfig(),
    )
    assert "lastLoggedEntry" not in cmd.update


@pytest.mark.asyncio
@patch("orchestrator.app.health_agent.copilotkit_emit_state", new_callable=AsyncMock)
@patch(
    "orchestrator.app.health_agent._call_agent_with_artifact",
    side_effect=RuntimeError("boom"),
)
async def test_tool_exception_sets_error_status(_call_mock, _emit_mock):
    from orchestrator.app.health_agent import ask_nutrition_agent

    state = {"messages": [], "toolCalls": []}
    cmd = await ask_nutrition_agent.ainvoke(
        {
            "name": "ask_nutrition_agent",
            "type": "tool_call",
            "id": "tc3",
            "args": {
                "message": "x",
                "skill": "log_meal",
                "state": state,
            },
        },
        config=_FakeRunnableConfig(),
    )
    assert cmd.update["toolCalls"][0]["status"] == "error"
    assert "boom" in cmd.update["toolCalls"][0]["error"]
    assert "lastLoggedEntry" not in cmd.update
