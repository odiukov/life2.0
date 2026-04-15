"""LangGraph ReAct agent — one generic tool per A2A peer."""
from __future__ import annotations

import uuid
import warnings
from typing import Literal

import httpx
from a2a.types import Message, Part, Role, Task, TextPart
from langchain_core.tools import tool

from shared.a2a_clients import get_client

from .llm import build_llm

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


async def _call_agent(agent: str, message: str, skill: str) -> str:
    text, _ = await _call_agent_with_artifact(agent, message, skill)
    return text


@tool
async def ask_sleep_agent(
    message: str,
    skill: Literal["log_sleep", "analyze_sleep", "get_sleep_recommendations"],
) -> str:
    """Call sleep-agent. Use 'log_sleep' to record a new entry, 'analyze_sleep' to
    discuss quality/trends, 'get_sleep_recommendations' for actionable advice."""
    return await _call_agent("sleep", message, skill)


@tool
async def ask_workout_agent(
    message: str,
    skill: Literal["log_workout", "analyze_workout", "get_workout_recommendations"],
) -> str:
    """Call workout-agent. Skills: log_workout / analyze_workout / get_workout_recommendations."""
    return await _call_agent("workout", message, skill)


@tool
async def ask_nutrition_agent(
    message: str,
    skill: Literal["log_meal", "analyze_nutrition", "get_nutrition_recommendations"],
) -> str:
    """Call nutrition-agent. Skills: log_meal / analyze_nutrition / get_nutrition_recommendations."""
    return await _call_agent("nutrition", message, skill)


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
    "You are a personal health assistant. You have three peer agents: sleep, workout, nutrition. "
    "Each tool accepts a skill parameter — pick the one that matches intent (log/analyze/recommend). "
    "For sync or briefing requests, use the dedicated tools. Be concise and actionable."
)


def create_health_agent():
    from langgraph.checkpoint.memory import MemorySaver
    llm = build_llm()
    tools = [ask_sleep_agent, ask_workout_agent, ask_nutrition_agent, sync_health_data, send_daily_briefing]
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.prebuilt import create_react_agent
        return create_react_agent(llm, tools, prompt=_SYSTEM_PROMPT, checkpointer=MemorySaver())
