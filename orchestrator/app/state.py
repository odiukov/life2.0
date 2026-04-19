"""Shared state schema for the orchestrator LangGraph agent.

Consumed by frontend via CopilotKit useCoAgent<HealthAgentState>({name:"default"}).
Keys are camelCase to match JS conventions.
"""
from __future__ import annotations

from typing import Annotated, Literal, NotRequired, TypedDict

from langchain_core.messages import AnyMessage
from langgraph.graph.message import add_messages
from langgraph.managed.is_last_step import RemainingSteps

ToolStatus = Literal["running", "done", "error"]


class ToolCall(TypedDict):
    id: str
    name: str
    skill: NotRequired[str]
    status: ToolStatus
    startedAt: str  # ISO8601
    endedAt: NotRequired[str]
    error: NotRequired[str]


class LogEntry(TypedDict):
    agent: Literal["sleep", "workout", "nutrition", "body", "mood"]
    skill: str
    summary: str
    timestamp: str


def _take_last(_a, b):
    return b


def _take_last_non_none(a, b):
    return b if b is not None else a


def _merge_tool_calls(
    a: list[ToolCall] | None, b: list[ToolCall] | None
) -> list[ToolCall]:
    """Merge tool-call lists by id, later value wins, stable order of first occurrence.

    Parallel tool nodes each read the same prior state and return `[*prior, their_own]`.
    A naive concat would duplicate the prior entries; last-wins would drop siblings.
    Merge-by-id is the only option that preserves one entry per tool invocation.
    """
    out: list[ToolCall] = []
    seen: dict[str, int] = {}
    for src in (a or [], b or []):
        for call in src:
            cid = call.get("id")
            if cid is None:
                out.append(call)
                continue
            if cid in seen:
                out[seen[cid]] = call
            else:
                seen[cid] = len(out)
                out.append(call)
    return out


class HealthAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    remaining_steps: NotRequired[RemainingSteps]
    currentStep: NotRequired[Annotated[str, _take_last]]
    activeAgent: NotRequired[Annotated[str | None, _take_last]]
    toolCalls: NotRequired[Annotated[list[ToolCall], _merge_tool_calls]]
    lastLoggedEntry: NotRequired[Annotated[LogEntry | None, _take_last_non_none]]
