"""LangGraph ReAct agent — one generic tool per A2A peer with CoAgent state streaming."""
from __future__ import annotations

import uuid
import warnings
from datetime import datetime, timezone
from typing import Annotated, Literal

import httpx
from a2a.types import Message, Part, Role, Task, TextPart
from copilotkit.langgraph import copilotkit_emit_state
from langchain_core.messages import ToolMessage
from langchain_core.runnables import RunnableConfig
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from shared.a2a_clients import get_client

from shared.llm import build_llm
from .state import HealthAgentState, LogEntry, ToolCall

_SYNC_SERVICE_URL = "http://sync-service:8080/sync"


def _resolve_url(agent: str) -> str | None:
    from .registry import get_agent_url
    return get_agent_url(agent)


def _extract_text_from_task(task: Task) -> str:
    for art in task.artifacts or []:
        for p in art.parts or []:
            root = getattr(p, "root", p)
            text = getattr(root, "text", None)
            if text:
                return text
    return ""


def _extract_text_from_message(msg: Message) -> str:
    for p in msg.parts or []:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None)
        if text:
            return text
    return ""


def _extract_log_entry_from_task(task: Task) -> dict | None:
    for art in task.artifacts or []:
        if art.name != "log_entry":
            continue
        for p in art.parts or []:
            root = getattr(p, "root", p)
            data = getattr(root, "data", None)
            if isinstance(data, dict) and "summary" in data and "timestamp" in data:
                return data
    return None


async def _call_agent_with_artifact(
    agent: str, message: str, skill: str
) -> tuple[str, dict | None]:
    url = _resolve_url(agent)
    if not url:
        return f"Agent '{agent}' is currently unavailable.", None
    try:
        client = await get_client(url)
        msg = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            message_id=str(uuid.uuid4()),
            metadata={"skillId": skill},
        )
        text = ""
        log_entry: dict | None = None
        async for resp in client.send_message(msg):
            if isinstance(resp, tuple):
                task, _update = resp
                if not text:
                    text = _extract_text_from_task(task)
                if log_entry is None:
                    log_entry = _extract_log_entry_from_task(task)
            elif isinstance(resp, Message):
                if not text:
                    text = _extract_text_from_message(resp)
        if not text:
            text = f"Agent '{agent}' returned no content."
        return text, log_entry
    except Exception as e:
        return f"Error calling {agent} agent: {e}", None


_MAX_TOOL_CALLS = 20


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _running_tool_call(tool_call_id: str, name: str, skill: str) -> ToolCall:
    return {
        "id": tool_call_id,
        "name": name,
        "skill": skill,
        "status": "running",
        "startedAt": _now_iso(),
    }


def _trim(calls: list[ToolCall]) -> list[ToolCall]:
    return calls[-_MAX_TOOL_CALLS:]


async def _run_peer_tool(
    *,
    agent: Literal["sleep", "workout", "nutrition", "body", "mood", "habits"],
    message: str,
    skill: str,
    tool_name: str,
    config: RunnableConfig,
    tool_call_id: str,
    state: HealthAgentState,
) -> Command:
    prev_calls = list(state.get("toolCalls") or [])
    running = _running_tool_call(tool_call_id, tool_name, skill)
    await copilotkit_emit_state(config, {
        **state,
        "currentStep": f"querying {agent} ({skill})",
        "activeAgent": agent,
        "toolCalls": _trim([*prev_calls, running]),
    })
    try:
        text, log_entry = await _call_agent_with_artifact(agent, message, skill)
        done_call: ToolCall = {**running, "status": "done", "endedAt": _now_iso()}
        update: dict = {
            "currentStep": "composing",
            "activeAgent": None,
            "toolCalls": _trim([*prev_calls, done_call]),
            "messages": [ToolMessage(content=text, tool_call_id=tool_call_id)],
        }
        if skill.startswith("log_") and log_entry:
            entry: LogEntry = {
                "agent": agent,
                "skill": skill,
                "summary": log_entry["summary"],
                "timestamp": log_entry["timestamp"],
            }
            update["lastLoggedEntry"] = entry
        return Command(update=update)
    except Exception as e:
        err_call: ToolCall = {
            **running, "status": "error", "endedAt": _now_iso(), "error": str(e)
        }
        return Command(update={
            "currentStep": "composing",
            "activeAgent": None,
            "toolCalls": _trim([*prev_calls, err_call]),
            "messages": [ToolMessage(content=f"Error: {e}", tool_call_id=tool_call_id)],
        })


@tool
async def ask_sleep_agent(
    message: str,
    skill: Literal["log_sleep", "analyze_sleep", "get_sleep_recommendations"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call sleep-agent. Use 'log_sleep' to record a new entry, 'analyze_sleep' to
    discuss quality/trends, 'get_sleep_recommendations' for actionable advice."""
    return await _run_peer_tool(
        agent="sleep", message=message, skill=skill, tool_name="ask_sleep_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_workout_agent(
    message: str,
    skill: Literal["log_workout", "analyze_workout", "get_workout_recommendations"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call workout-agent. Skills: log_workout / analyze_workout / get_workout_recommendations."""
    return await _run_peer_tool(
        agent="workout", message=message, skill=skill, tool_name="ask_workout_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_nutrition_agent(
    message: str,
    skill: Literal["log_meal", "analyze_nutrition", "get_nutrition_recommendations"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call nutrition-agent. Skills: log_meal / analyze_nutrition / get_nutrition_recommendations."""
    return await _run_peer_tool(
        agent="nutrition", message=message, skill=skill, tool_name="ask_nutrition_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_body_agent(
    message: str,
    skill: Literal["get_latest_body", "analyze_body_trend"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call body-agent. Skills: get_latest_body (current weight/fat/muscle snapshot) or
    analyze_body_trend (dynamics with nutrition/workout correlation)."""
    return await _run_peer_tool(
        agent="body", message=message, skill=skill, tool_name="ask_body_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_mood_agent(
    message: str,
    skill: Literal["log_mood", "analyze_mood", "get_recommendations", "coach_session"],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call mood-agent. Skills:
    log_mood (record a new mood entry from free-text or /mood),
    analyze_mood (trend over the last N days),
    get_recommendations (short actionable advice),
    coach_session (record a completed coach session aggregate — usually driven by
    the telegram bot, not by the orchestrator)."""
    return await _run_peer_tool(
        agent="mood", message=message, skill=skill, tool_name="ask_mood_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_habits_agent(
    message: str,
    skill: Literal[
        "define_habit", "log_habit_check", "analyze_habit",
        "get_streak_summary", "archive_habit",
    ],
    config: RunnableConfig,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call habits-agent. Skills:
    define_habit (create a new habit from '/habit new ...' free text),
    log_habit_check (record one check-in; user must use the /habit command — do NOT
      call this from free text),
    analyze_habit (adherence summary for a window, default 7 days),
    get_streak_summary (deterministic one-liner of current streaks per habit),
    archive_habit (soft-delete a habit)."""
    return await _run_peer_tool(
        agent="habits", message=message, skill=skill,
        tool_name="ask_habits_agent",
        config=config, tool_call_id=tool_call_id, state=state,
    )


@tool
async def sync_health_data() -> str:
    """Synchronize health data from Garmin and Yazio."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(_SYNC_SERVICE_URL)
            resp.raise_for_status()
            data = resp.json()
            text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
            if data.get("errors"):
                text += f" Errors: {'; '.join(data['errors'][:3])}"
            return text
    except Exception as e:
        return f"Sync failed: {e}"


@tool
async def send_daily_briefing() -> str:
    """Generate and send the daily health briefing via Telegram."""
    from .registry import get_registry
    from .briefing import run_briefing
    try:
        await run_briefing(get_registry())
        return "Daily health briefing generated and sent via Telegram."
    except Exception as e:
        return f"Briefing failed: {e}"


_SYSTEM_PROMPT = (
    "You are a personal health assistant. You have six peer agents: sleep, workout, "
    "nutrition, body, mood, habits. Each tool accepts a skill parameter — pick the one "
    "that matches intent (log/analyze/recommend/query). Route mood/feelings/stress/journal "
    "language to the mood agent. For habits, only invoke log_habit_check when the user "
    "message starts with '/habit' or a habit inline-button callback payload — free text "
    "like 'I read today' must NOT log a habit. Analyze/streak queries ('my streak', "
    "'how are my habits') → analyze_habit / get_streak_summary. "
    "\n\n"
    "You also have live Google Calendar tools (list events, search, get, create, update, "
    "delete). Use them for \"what's on my calendar\" / \"when am I free\" / \"find me time "
    "for X\" / \"add X at time T\" intents. "
    "\n\n"
    "For destructive calendar operations (create, update, delete), always paraphrase the "
    "intended action back to the user and wait for explicit confirmation before executing. "
    "For read-only calendar queries (list, search, get), answer directly without confirmation. "
    "\n\n"
    "For sync or briefing requests, use the dedicated tools. Be concise and actionable."
)


async def create_health_agent():
    """Build the ReAct agent. Async because MCP tool discovery is async."""
    from langgraph.checkpoint.memory import MemorySaver
    from .mcp_tools import load_mcp_tools

    llm = build_llm()
    peer_tools = [
        ask_sleep_agent,
        ask_workout_agent,
        ask_nutrition_agent,
        ask_body_agent,
        ask_mood_agent,
        ask_habits_agent,
        sync_health_data,
        send_daily_briefing,
    ]
    mcp_tools = await load_mcp_tools()
    tools = peer_tools + mcp_tools

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.prebuilt import create_react_agent
        return create_react_agent(
            llm,
            tools,
            prompt=_SYSTEM_PROMPT,
            state_schema=HealthAgentState,
            checkpointer=MemorySaver(),
        )
