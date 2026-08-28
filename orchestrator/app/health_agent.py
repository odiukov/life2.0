"""LangGraph ReAct agent — one generic tool per A2A peer with CoAgent state streaming."""
from __future__ import annotations

import logging
import re
import uuid
import warnings
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Annotated, Literal
from zoneinfo import ZoneInfo

from shared.skill_ids import (
    BodySkillId, HabitsSkillId, RecoverySkillId, MedicationSkillId,
)

# Conversational-tool subsets: the full XxxSkillId aliases may include skills
# not exposed via the LLM tool interface; narrow here to match peer SKILLS exactly.
_SleepToolSkillId = Literal["log_sleep", "analyze_sleep", "get_sleep_recommendations"]
_WorkoutToolSkillId = Literal["log_workout", "analyze_workout", "get_workout_recommendations"]
_NutritionToolSkillId = Literal[
    "log_meal", "analyze_nutrition", "get_nutrition_recommendations", "set_body_profile"
]
_MoodToolSkillId = Literal[
    "log_mood", "analyze_mood", "get_mood_recommendations", "coach_session"
]

import httpx
from a2a.types import Message, Part, Role, Task, TextPart
from langchain_core.messages import HumanMessage, SystemMessage, ToolMessage
from langchain_core.tools import tool, InjectedToolCallId
from langgraph.prebuilt import InjectedState
from langgraph.types import Command

from shared.a2a_clients import get_client

from shared.llm import build_llm
from .state import HealthAgentState, LogEntry, ToolCall

logger = logging.getLogger(__name__)

_SYNC_SERVICE_URL = "http://sync-service:8080/sync"
_FALLBACK_TZ = datetime.now().astimezone().tzinfo


def _zoneinfo_or_fallback(timezone_name: str | None):
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            pass
    return _FALLBACK_TZ


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


def _extract_consulted_peers_from_task(task: Task) -> list[str] | None:
    """Read the `consulted_peers` artifact emitted by sleep/workout/nutrition
    executors. Returns None if the artifact is absent (older agents) so the
    caller can distinguish "no peers" from "agent didn't report"."""
    for art in task.artifacts or []:
        if art.name != "consulted_peers":
            continue
        for p in art.parts or []:
            root = getattr(p, "root", p)
            data = getattr(root, "data", None)
            if isinstance(data, dict) and isinstance(data.get("peers"), list):
                return [str(x) for x in data["peers"]]
    return None


async def _call_agent_with_artifact(
    agent: str, message: str, skill: str, user_id: str | None = None,
    focus_sources: list[str] | None = None,
) -> tuple[str, dict | None, list[str] | None]:
    """Send one A2A message to a peer agent.

    Returns (text, log_entry, consulted_peers) where consulted_peers is the
    list of peers the called agent itself consulted via its peer_artifacts
    fan-out (sleep/workout/nutrition only — others omit the artifact and we
    return None there)."""
    url = _resolve_url(agent)
    if not url:
        return f"Agent '{agent}' is currently unavailable.", None, None
    try:
        client = await get_client(url)
        metadata: dict = {"skillId": skill}
        if user_id:
            metadata["user_id"] = user_id
        if focus_sources:
            metadata["focus_sources"] = list(focus_sources)
        msg = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=message))],
            message_id=str(uuid.uuid4()),
            metadata=metadata,
        )
        text = ""
        log_entry: dict | None = None
        consulted_peers: list[str] | None = None
        async for resp in client.send_message(msg):
            if isinstance(resp, tuple):
                task, _update = resp
                if not text:
                    text = _extract_text_from_task(task)
                if log_entry is None:
                    log_entry = _extract_log_entry_from_task(task)
                if consulted_peers is None:
                    consulted_peers = _extract_consulted_peers_from_task(task)
            elif isinstance(resp, Message):
                if not text:
                    text = _extract_text_from_message(resp)
        if not text:
            text = f"Agent '{agent}' returned no content."
        return text, log_entry, consulted_peers
    except Exception as e:
        return f"Error calling {agent} agent: {e}", None, None


_MAX_TOOL_CALLS = 20


# Cue patterns the user uses to ground a question in another domain.
# Either a cue word + a domain keyword, OR a bare list of two+ domains
# ("сон, питание, тренировки") signals cross-domain framing.
_FOCUS_CUE_RE = re.compile(
    r"учитыва|на основе|исходя из|с учё?том|considering|based on|"
    r"given (?:my|the)|in light of|relative to|по отношению к|"
    r"в контексте|in context of",
    re.IGNORECASE,
)

_DOMAIN_KEYWORDS: dict[str, tuple[str, ...]] = {
    "sleep": ("сон", "сна", "сну", "спал", "сплю", "спан", "sleep", "слипа"),
    "workout": (
        "спорт", "тренир", "трениров", "workout", "training", "exercise",
        "упражн", "кардио", "cardio", "пробеж", "run ", "running", "лифт",
    ),
    "nutrition": (
        "питан", "еда", "ел ", "ела ", "ем ", "пищ", "калор", "kcal",
        "macros", "макро", "белок", "protein", "carb", "углевод",
        "nutrition", "meal", "ужин", "обед", "завтрак", "перекус",
        "food", "intake", "diet ", "diet,", "diet.",
    ),
    "recovery": (
        "восстан", "recovery", "hrv", "стресс", "stress", "усталост",
        "readiness", "готовност", "перетрен",
    ),
}

_CALENDAR_TITLE_STOPWORDS = {
    "delete", "remove", "event", "calendar", "please", "the", "a", "an",
    "удали", "удалить", "убери", "событие", "ивент", "встречу", "встреча",
    "календарь", "календаре", "пожалуйста",
}


def _calendar_title_tokens(value: str) -> set[str]:
    raw = re.findall(r"[\w]+", value.lower(), flags=re.UNICODE)
    return {token for token in raw if token and token not in _CALENDAR_TITLE_STOPWORDS}


def _calendar_title_matches(query: str, summary: str) -> bool:
    q_norm = " ".join(re.findall(r"[\w]+", query.lower(), flags=re.UNICODE))
    s_norm = " ".join(re.findall(r"[\w]+", summary.lower(), flags=re.UNICODE))
    if not q_norm or not s_norm:
        return False
    if q_norm in s_norm or s_norm in q_norm:
        return True
    q_tokens = _calendar_title_tokens(query)
    s_tokens = _calendar_title_tokens(summary)
    if not q_tokens or not s_tokens:
        return False
    return bool(q_tokens & s_tokens)


def _autodetect_focus_sources(
    state: HealthAgentState | None,
    primary: str,
    candidates: tuple[str, ...],
) -> list[str]:
    """Scan the latest user HumanMessage in `state` for cross-domain references
    and return peers (∈ candidates, ≠ primary) the user explicitly cited.

    Two trigger paths:
      1. cue word ("учитывая", "based on", …) + at least one domain keyword,
      2. two or more distinct domain keywords mentioned together (free-form
         enumeration like "как мой сон и питание").

    Deterministic — never relies on the orchestrator LLM remembering to pass
    `focus_sources`. Returned in a stable order matching `candidates` so the
    behavior is reproducible across calls.
    """
    if state is None:
        return []
    msgs = state.get("messages") or []
    last_user_text: str | None = None
    for msg in reversed(msgs):
        if isinstance(msg, HumanMessage):
            content = getattr(msg, "content", "")
            if isinstance(content, str) and content.strip():
                last_user_text = content
                break
    if not last_user_text:
        return []
    text = last_user_text.lower()
    matched: list[str] = []
    for peer in candidates:
        if peer == primary:
            continue
        if any(kw in text for kw in _DOMAIN_KEYWORDS.get(peer, ())):
            matched.append(peer)
    if not matched:
        return []
    cue_present = bool(_FOCUS_CUE_RE.search(text))
    primary_referenced = any(
        kw in text for kw in _DOMAIN_KEYWORDS.get(primary, ())
    )
    # cue word OR (multiple domains AND user mentioned the primary domain too)
    # — the latter handles "как мой сон и питание" style enumeration.
    if cue_present or (len(matched) >= 1 and primary_referenced):
        return matched
    if len(matched) >= 2:
        return matched
    return []


def _merge_focus_sources(
    explicit: list[str] | None,
    auto: list[str],
) -> list[str] | None:
    """Union explicit (LLM-passed) + auto-detected, preserving order, dedup'd."""
    if not explicit and not auto:
        return None
    seen: dict[str, None] = {}
    for src in (explicit or [], auto):
        for peer in src:
            if peer not in seen:
                seen[peer] = None
    return list(seen.keys()) or None


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


def _user_uuid_from_state(state: HealthAgentState) -> uuid.UUID:
    user_id = state.get("userId")
    if not user_id:
        raise ValueError("missing userId in graph state")
    return uuid.UUID(str(user_id))


def _format_calendar_time(value: str) -> str:
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return value
    return parsed.strftime("%H:%M")


def _format_calendar_event(ev: dict) -> str | None:
    summary = ev.get("summary") or "Untitled"
    event_id = ev.get("id")
    suffix = f" (event_id: {event_id})" if event_id else ""
    if ev.get("all_day"):
        return f"• all day: {summary}{suffix}"
    start = ev.get("start")
    end = ev.get("end")
    if not start or not end:
        return None
    return f"• {_format_calendar_time(str(start))}-{_format_calendar_time(str(end))}: {summary}{suffix}"


def _calendar_result_summary(action: str, data: dict | None) -> str:
    if isinstance(data, dict):
        bits = [f"{action} calendar event"]
        if summary := data.get("summary"):
            bits.append(f"'{summary}'")
        if event_id := data.get("id"):
            bits.append(f"(id: {event_id})")
        if link := data.get("htmlLink"):
            bits.append(str(link))
        return " ".join(bits) + "."
    return f"{action} calendar event."


_CALENDAR_NOT_CONNECTED = (
    "Calendar changes are not available in this chat. "
    "Reconnect Google Calendar and try again."
)


async def _run_calendar_call(state: HealthAgentState, action: str, call):
    """Run one google_calendar_api coroutine factory, mapping failures to text.

    `call` takes the resolved user_id so the token lookup stays inside the
    try block — a revoked refresh token surfaces as CalendarNotConnected.
    """
    from .google_calendar_api import CalendarApiError, CalendarNotConnected

    try:
        user_id = _user_uuid_from_state(state)
    except Exception:
        return "Calendar is unavailable in this chat because the user session is missing."

    try:
        result = await call(user_id)
    except CalendarNotConnected:
        return _CALENDAR_NOT_CONNECTED
    except CalendarApiError as e:
        if e.status_code in (401, 403):
            return _CALENDAR_NOT_CONNECTED
        logger.warning("calendar %s failed: %s", action.lower(), e)
        return f"Calendar {action.lower()} failed: Google returned {e.status_code}."
    except Exception as e:
        logger.warning("calendar %s failed: %s", action.lower(), e)
        return f"Calendar {action.lower()} failed: {e}"
    return _calendar_result_summary(action, result)


async def _run_peer_tool(
    *,
    agent: Literal["sleep", "workout", "nutrition", "body", "mood", "habits", "recovery", "medication"],
    message: str,
    skill: str,
    tool_name: str,
    tool_call_id: str,
    state: HealthAgentState,
    focus_sources: list[str] | None = None,
) -> Command:
    prev_calls = list(state.get("toolCalls") or [])
    running = _running_tool_call(tool_call_id, tool_name, skill)
    user_id = state.get("userId")
    try:
        text, log_entry, consulted_peers = await _call_agent_with_artifact(
            agent, message, skill, user_id=user_id, focus_sources=focus_sources,
        )
        done_call: ToolCall = {**running, "status": "done", "endedAt": _now_iso()}
        if consulted_peers is not None:
            done_call["consultedPeers"] = consulted_peers
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
    skill: _SleepToolSkillId,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
    focus_sources: list[str] | None = None,
) -> Command:
    """Call sleep-agent. Use 'log_sleep' to record a new entry, 'analyze_sleep' to
    discuss quality/trends, 'get_sleep_recommendations' for actionable advice.
    Pass focus_sources=['workout','nutrition','recovery',...] when the user explicitly cites
    those domains as the basis for advice — otherwise omit and the agent uses minimal context."""
    auto = _autodetect_focus_sources(state, "sleep", ("workout", "nutrition"))
    merged = _merge_focus_sources(focus_sources, auto)
    return await _run_peer_tool(
        agent="sleep", message=message, skill=skill, tool_name="ask_sleep_agent",
        tool_call_id=tool_call_id, state=state, focus_sources=merged,
    )


@tool
async def ask_workout_agent(
    message: str,
    skill: _WorkoutToolSkillId,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
    focus_sources: list[str] | None = None,
) -> Command:
    """Call workout-agent. Skills: log_workout / analyze_workout / get_workout_recommendations.
    Pass focus_sources=['sleep','nutrition','recovery',...] when the user explicitly cites
    those domains as the basis for advice — otherwise omit and the agent uses minimal context."""
    auto = _autodetect_focus_sources(state, "workout", ("sleep", "nutrition"))
    merged = _merge_focus_sources(focus_sources, auto)
    return await _run_peer_tool(
        agent="workout", message=message, skill=skill, tool_name="ask_workout_agent",
        tool_call_id=tool_call_id, state=state, focus_sources=merged,
    )


@tool
async def ask_nutrition_agent(
    message: str,
    skill: _NutritionToolSkillId,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
    focus_sources: list[str] | None = None,
) -> Command:
    """Call nutrition-agent. Skills: log_meal / analyze_nutrition / get_nutrition_recommendations /
    set_body_profile (save height, age, sex, activity_level, or calorie_goal_override so the
    agent can calculate an accurate daily calorie goal / TDEE).
    Pass focus_sources=['workout','sleep','recovery',...] when the user explicitly cites
    those domains as the basis for advice — otherwise omit and the agent uses minimal context."""
    auto = _autodetect_focus_sources(state, "nutrition", ("sleep", "workout"))
    merged = _merge_focus_sources(focus_sources, auto)
    return await _run_peer_tool(
        agent="nutrition", message=message, skill=skill, tool_name="ask_nutrition_agent",
        tool_call_id=tool_call_id, state=state, focus_sources=merged,
    )


@tool
async def ask_body_agent(
    message: str,
    skill: BodySkillId,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call body-agent. Skills: get_latest_body (current weight/fat/muscle snapshot) or
    analyze_body_trend (dynamics with nutrition/workout correlation)."""
    return await _run_peer_tool(
        agent="body", message=message, skill=skill, tool_name="ask_body_agent",
        tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_mood_agent(
    message: str,
    skill: _MoodToolSkillId,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call mood-agent. Skills:
    log_mood (record a new mood entry from free-text or /mood),
    analyze_mood (trend over the last N days),
    get_mood_recommendations (short actionable advice),
    coach_session (record a completed coach session aggregate — usually driven by
    the chat coach loop, not by the orchestrator)."""
    return await _run_peer_tool(
        agent="mood", message=message, skill=skill, tool_name="ask_mood_agent",
        tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_habits_agent(
    message: str,
    skill: HabitsSkillId,
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
        tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_recovery_agent(
    message: str,
    skill: RecoverySkillId,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call recovery-agent. Skills:
    get_readiness (today's bucket + HRV/RHR/stress/body-battery with deltas),
    analyze_recovery_trend (per-metric 7-day trend + correlations),
    get_recommendations (2–3 actionable recovery recommendations)."""
    return await _run_peer_tool(
        agent="recovery", message=message, skill=skill,
        tool_name="ask_recovery_agent",
        tool_call_id=tool_call_id, state=state,
    )


@tool
async def ask_medication_agent(
    message: str,
    skill: MedicationSkillId,
    tool_call_id: Annotated[str, InjectedToolCallId],
    state: Annotated[HealthAgentState, InjectedState],
) -> Command:
    """Call medication-agent. Skills:
    define_medication (parse free text into a structured medication and persist),
    log_medication (record one dose taken; resolves medication by name),
    list_active (deterministic list of currently tracked medications),
    analyze_adherence (LLM summary of adherence over a window, default 14 days),
    archive_medication (soft-delete a medication by name)."""
    return await _run_peer_tool(
        agent="medication", message=message, skill=skill,
        tool_name="ask_medication_agent",
        tool_call_id=tool_call_id, state=state,
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
async def query_calendar_events(
    target_date: str,
    state: Annotated[HealthAgentState, InjectedState],
) -> str:
    """List the user's Google Calendar events for one day.

    target_date must be YYYY-MM-DD. Use this for "what's on my calendar",
    "what meetings do I have", and read-only availability questions.
    """
    try:
        day = date.fromisoformat(target_date)
    except ValueError:
        return "Calendar query failed: target_date must be YYYY-MM-DD."

    try:
        user_id = _user_uuid_from_state(state)
    except Exception:
        return "Calendar is unavailable in this chat because the user session is missing."

    from .calendar_context import fetch_calendar_events

    timezone_name = state.get("userTimezone")
    events = await fetch_calendar_events(
        user_id,
        day,
        max_results=20,
        timezone_name=timezone_name if isinstance(timezone_name, str) else None,
    )
    if not events:
        return f"No calendar events found for {target_date}."

    lines = [f"Calendar events for {target_date}:"]
    lines.extend(line for ev in events if (line := _format_calendar_event(ev)))
    return "\n".join(lines)


@tool
async def create_calendar_event(
    summary: str,
    start: str,
    end: str,
    state: Annotated[HealthAgentState, InjectedState],
    calendar_id: str | None = None,
    description: str | None = None,
    attendees: list[str] | None = None,
) -> str:
    """Create a Google Calendar event after explicit user confirmation.

    start/end must be ISO 8601 datetimes with timezone offsets. Use this only
    after the user confirms the exact event title and time.
    """
    from .google_calendar_api import create_event

    kwargs = {"summary": summary, "start": start, "end": end}
    if description:
        kwargs["description"] = description
    if attendees:
        kwargs["attendees"] = attendees
    if calendar_id:
        kwargs["calendar_id"] = calendar_id
    return await _run_calendar_call(
        state, "Created", lambda user_id: create_event(user_id, **kwargs)
    )


@tool
async def update_calendar_event(
    event_id: str,
    patch: dict,
    state: Annotated[HealthAgentState, InjectedState],
    calendar_id: str | None = None,
) -> str:
    """Update a Google Calendar event after explicit user confirmation.

    patch is a Google Calendar event patch object. Use this only after the user
    confirms the target event and the exact change.
    """
    from .google_calendar_api import patch_event

    kwargs = {"event_id": event_id, "patch": patch}
    if calendar_id:
        kwargs["calendar_id"] = calendar_id
    return await _run_calendar_call(
        state, "Updated", lambda user_id: patch_event(user_id, **kwargs)
    )


@tool
async def delete_calendar_event(
    event_id: str,
    state: Annotated[HealthAgentState, InjectedState],
    calendar_id: str | None = None,
) -> str:
    """Delete a Google Calendar event after explicit user confirmation.

    Use this only after the user confirms the exact event to delete.
    """
    return await _run_calendar_call(
        state, "Deleted", _delete_call(event_id, calendar_id)
    )


def _delete_call(event_id: str, calendar_id: str | None):
    from .google_calendar_api import delete_event

    kwargs = {"event_id": event_id}
    if calendar_id:
        kwargs["calendar_id"] = calendar_id
    return lambda user_id: delete_event(user_id, **kwargs)


@tool
async def delete_calendar_event_by_title(
    target_date: str,
    title_query: str,
    state: Annotated[HealthAgentState, InjectedState],
    calendar_id: str | None = None,
) -> str:
    """Delete one calendar event by matching title on a specific day after confirmation.

    Use this when the user names an event but does not provide an event_id. If
    more than one event matches, do not delete; ask the user to disambiguate.
    """
    try:
        day = date.fromisoformat(target_date)
    except ValueError:
        return "Calendar deletion failed: target_date must be YYYY-MM-DD."
    try:
        user_id = _user_uuid_from_state(state)
    except Exception:
        return "Calendar is unavailable in this chat because the user session is missing."

    from .calendar_context import fetch_calendar_events

    timezone_name = state.get("userTimezone")
    events = await fetch_calendar_events(
        user_id,
        day,
        max_results=50,
        timezone_name=timezone_name if isinstance(timezone_name, str) else None,
    )
    needle = title_query.strip().lower()
    matches = [
        ev for ev in events
        if needle and _calendar_title_matches(title_query, str(ev.get("summary") or "")) and ev.get("id")
    ]
    if not matches:
        lines = [f"No matching calendar event found for '{title_query}' on {target_date}."]
        visible = [line for ev in events if (line := _format_calendar_event(ev))]
        if visible:
            lines.append("Visible events:")
            lines.extend(visible)
        return "\n".join(lines)
    if len(matches) > 1:
        lines = [f"Found multiple matching calendar events for '{title_query}' on {target_date}:"]
        lines.extend(line for ev in matches if (line := _format_calendar_event(ev)))
        return "\n".join(lines)

    event_id = str(matches[0]["id"])
    return await _run_calendar_call(
        state, "Deleted", _delete_call(event_id, calendar_id)
    )


@tool
async def query_finance_summary(
    month: str,
    state: Annotated[HealthAgentState, InjectedState],
) -> str:
    """Return income + spending summary for a given month (YYYY-MM, e.g. '2026-04').
    Use for 'сколько пришло в апреле', 'how much did I earn in march', etc.
    Currencies are never converted — each currency is reported separately.
    """
    from . import finance_queries

    user_id = _user_uuid_from_state(state)
    income = await finance_queries.income_for_month(user_id, month)
    spending = await finance_queries.spending_by_category(user_id, month)

    if not income and not spending:
        return f"За {month} транзакций нет."

    lines = [f"Финансы за {month}:"]
    if income:
        bits = [f"+{amt} {cur}" for cur, amt in sorted(income.items())]
        lines.append("• Пришло: " + ", ".join(bits))
    spend_by_cur: dict[str, Decimal] = {}
    for _cat, cur, amt in spending:
        spend_by_cur[cur] = spend_by_cur.get(cur, Decimal("0")) + amt
    if spend_by_cur:
        bits = [f"−{amt} {cur}" for cur, amt in sorted(spend_by_cur.items())]
        lines.append("• Ушло: " + ", ".join(bits))
    if spending:
        top = spending[:3]
        lines.append("• Топ категорий: " + " · ".join(
            f"{name} {amt} {cur}" for name, cur, amt in top
        ))
    return "\n".join(lines)


@tool
async def query_finance_categories(
    month: str,
    state: Annotated[HealthAgentState, InjectedState],
) -> str:
    """Return spending breakdown by category for a month (YYYY-MM).
    Use for 'куда ушли деньги в апреле', 'where did money go'.
    """
    from . import finance_queries
    user_id = _user_uuid_from_state(state)
    rows = await finance_queries.spending_by_category(user_id, month)
    if not rows:
        return f"За {month} нет затрат с категорией."
    lines = [f"Траты по категориям за {month}:"]
    for name, cur, amt in rows:
        lines.append(f"• {name}: {amt} {cur}")
    return "\n".join(lines)


@tool
async def query_finance_runway(
    state: Annotated[HealthAgentState, InjectedState],
) -> str:
    """Return current balance + average daily burn + runway in days, per currency.
    Use for 'хватит ли до конца месяца', 'how many days I have left', etc.
    """
    from . import finance_queries
    user_id = _user_uuid_from_state(state)
    data = await finance_queries.runway(user_id, avg_window_days=30)
    if not data:
        return "Нет данных по транзакциям."
    lines = []
    for cur, info in sorted(data.items()):
        bal = info["balance"]
        burn = info["avg_daily_burn"]
        days = info["days"]
        if days is None:
            lines.append(f"• {cur}: баланс {bal}, расходов за 30 дней нет.")
        else:
            lines.append(
                f"• {cur}: баланс {bal}, средний расход {burn}/день, хватит на ~{days} дней."
            )
    return "\n".join(lines)


_SYSTEM_PROMPT = (
    "You are a personal health assistant. You have eight peer agents: sleep, workout, "
    "nutrition, body, mood, habits, recovery, medication. Each tool accepts a skill parameter — pick "
    "the one that matches intent (log/analyze/recommend/query). Route mood/feelings/stress/journal "
    "language to the mood agent. For habits, only invoke log_habit_check when the user "
    "message starts with '/habit' or a habit inline-button callback payload — free text "
    "like 'I read today' must NOT log a habit. Analyze/streak queries ('my streak', "
    "'how are my habits') → analyze_habit / get_streak_summary. "
    "\n\n"
    "Three tools — ask_sleep_agent, ask_workout_agent, ask_nutrition_agent — accept an optional "
    "focus_sources parameter. Pass it ONLY when the user explicitly cites another domain as the "
    "basis for advice (e.g. 'посоветуй тренировку на основе сна и питания' → "
    "ask_workout_agent(focus_sources=['sleep','nutrition'])). For neutral requests ('посоветуй "
    "тренировку', 'should I run today'), omit focus_sources — the agent will answer from its own "
    "data, faster and cheaper. For readiness questions ('should I train hard today', 'am I "
    "recovered'), call ask_recovery_agent first; the user is asking about recovery state, not "
    "workouts directly. "
    "\n\n"
    "Use query_calendar_events for read-only Google Calendar intents like "
    "\"what's on my calendar\", \"what meetings do I have\", and \"when am I free\". "
    "\n\n"
    "For destructive calendar operations (create, update, delete), always paraphrase the "
    "intended action back to the user and wait for explicit confirmation before executing "
    "create_calendar_event, update_calendar_event, delete_calendar_event, or "
    "delete_calendar_event_by_title. For delete requests where the user names an event "
    "but no event_id is available, use delete_calendar_event_by_title with the resolved date. "
    "For read-only calendar queries, answer directly without confirmation. "
    "\n\n"
    "You also have live Home Assistant tools exposed via MCP. GetLiveContext is read-only "
    "— use it for questions like \"what's the temperature in the bedroom\" or \"is the "
    "hallway light on\" and answer directly without confirmation. "
    "\n\n"
    "For state-changing Home Assistant tools (HassTurnOn, HassTurnOff, HassLightSet, "
    "HassClimateSetTemperature, HassListAddItem, and any other mutation Hass* tool), always "
    "paraphrase the intended action back to the user in their language (e.g. \"включу свет "
    "в гостиной, ок?\") and wait for explicit confirmation (\"да\", \"ок\", \"ага\") before "
    "invoking the tool. Only entities the user has exposed via HA Settings → Voice assistants "
    "will be visible; if a requested entity isn't available, say so. "
    "\n\n"
    "You also have finance tools (query_finance_summary, query_finance_categories, "
    "query_finance_runway). Use them for questions about income, spending, or cash "
    "runway. Month format is YYYY-MM. "
    "\n\n"
    "For sync requests, use the dedicated tools. Be concise and actionable."
    "\n\n"
    "When the user mentions their height, age, sex (male/female), activity level "
    "(sedentary/light/moderate/active/very_active), or wants to set a calorie goal override, "
    "call ask_nutrition_agent with skill=set_body_profile. Pass the raw user message — the "
    "nutrition agent will extract and validate the fields. Do not ask for confirmation; "
    "just call the tool and relay the response."
)


def _build_system_prompt(now: datetime | None = None, timezone_name: str | None = None) -> str:
    tz = _zoneinfo_or_fallback(timezone_name)
    now_local = (now or datetime.now(tz)).astimezone(tz)
    return (
        f"Current date: {now_local.date().isoformat()} "
        f"({now_local.tzinfo.key if hasattr(now_local.tzinfo, 'key') else now_local.tzname()}). "
        "Resolve today/tomorrow/yesterday from this date before choosing tool arguments. "
        "For calendar questions, pass the resolved YYYY-MM-DD as query_calendar_events.target_date.\n\n"
        f"{_SYSTEM_PROMPT}"
    )


def _prompt_with_current_date(state: HealthAgentState):
    timezone_name = state.get("userTimezone")
    return [
        SystemMessage(content=_build_system_prompt(
            timezone_name=timezone_name if isinstance(timezone_name, str) else None
        )),
        *(state.get("messages") or []),
    ]


async def create_health_agent(checkpointer=None):
    """Build the ReAct agent. Async because MCP tool discovery is async.

    If `checkpointer` is None, falls back to an in-process MemorySaver.
    main.lifespan passes in an AsyncPostgresSaver for durable state.
    """
    from langgraph.checkpoint.memory import MemorySaver
    from .mcp_tools import load_mcp_tools

    if checkpointer is None:
        checkpointer = MemorySaver()

    llm = build_llm()
    peer_tools = [
        ask_sleep_agent,
        ask_workout_agent,
        ask_nutrition_agent,
        ask_body_agent,
        ask_mood_agent,
        ask_habits_agent,
        ask_recovery_agent,
        ask_medication_agent,
        sync_health_data,
        query_calendar_events,
        create_calendar_event,
        update_calendar_event,
        delete_calendar_event,
        delete_calendar_event_by_title,
        query_finance_summary,
        query_finance_categories,
        query_finance_runway,
    ]
    mcp_tools = await load_mcp_tools()
    tools = peer_tools + mcp_tools

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.prebuilt import create_react_agent
        return create_react_agent(
            llm,
            tools,
            prompt=_prompt_with_current_date,
            state_schema=HealthAgentState,
            checkpointer=checkpointer,
        )
