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
    agent: Literal["sleep", "workout", "nutrition"]
    skill: str
    summary: str
    timestamp: str


class HealthAgentState(TypedDict):
    messages: Annotated[list[AnyMessage], add_messages]
    remaining_steps: NotRequired[RemainingSteps]
    currentStep: NotRequired[str]
    activeAgent: NotRequired[str | None]
    toolCalls: NotRequired[list[ToolCall]]
    lastLoggedEntry: NotRequired[LogEntry | None]
