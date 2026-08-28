"""Reducer tests for HealthAgentState.

Parallel tool execution (LLM requests multiple tool_calls in one AIMessage) makes
LangGraph run several tool nodes in the same step. Each returns a Command(update=...)
that touches the same state keys. Without reducers, this raises
INVALID_CONCURRENT_GRAPH_UPDATE.
"""
from orchestrator.app.state import (
    _merge_tool_calls,
    _take_last,
    _take_last_non_none,
)


def test_take_last_picks_right_value():
    assert _take_last("a", "b") == "b"
    assert _take_last(None, "x") == "x"
    assert _take_last("x", None) is None


def test_take_last_non_none_keeps_prior_when_right_is_none():
    assert _take_last_non_none({"summary": "x"}, None) == {"summary": "x"}
    assert _take_last_non_none(None, {"summary": "y"}) == {"summary": "y"}
    assert _take_last_non_none({"summary": "x"}, {"summary": "y"}) == {"summary": "y"}


def test_merge_tool_calls_deduplicates_shared_prior_entries():
    """Two parallel tools each read the same prior state and emit
    [*prior, their_own]. Merge must produce prior + A + B, not 2x prior."""
    prior = [{"id": "p1", "name": "x", "status": "done", "startedAt": "t0"}]
    left = prior + [{"id": "a", "name": "sleep", "status": "done", "startedAt": "t1"}]
    right = prior + [{"id": "b", "name": "workout", "status": "done", "startedAt": "t1"}]

    merged = _merge_tool_calls(left, right)

    ids = [c["id"] for c in merged]
    assert ids == ["p1", "a", "b"]


def test_merge_tool_calls_later_entry_wins_on_same_id():
    running = {"id": "x", "name": "sleep", "status": "running", "startedAt": "t0"}
    done = {"id": "x", "name": "sleep", "status": "done", "startedAt": "t0", "endedAt": "t1"}

    merged = _merge_tool_calls([running], [done])

    assert merged == [done]


def test_merge_tool_calls_handles_none_inputs():
    assert _merge_tool_calls(None, None) == []
    entry = {"id": "a", "name": "x", "status": "done", "startedAt": "t"}
    assert _merge_tool_calls(None, [entry]) == [entry]
    assert _merge_tool_calls([entry], None) == [entry]
