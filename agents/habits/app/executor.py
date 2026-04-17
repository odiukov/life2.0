"""HabitsAgentExecutor — dispatches habit skills, computes streaks deterministically."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact,
    DataPart,
    Message,
    Part,
    Role,
    TaskArtifactUpdateEvent,
    TaskState,
    TaskStatus,
    TaskStatusUpdateEvent,
    TextPart,
)
from langchain_core.messages import HumanMessage

from shared.db import fetch_habit_logs, insert_log, insert_task_record
from shared.llm import build_llm
from shared.vector import upsert_memory

from . import registry
from .skills import SKILL_PROMPTS

_LLM = None
logger = logging.getLogger(__name__)
_LOG_ENTRY_SUMMARY_MAX = 120
_DAY_TZ = ZoneInfo("Europe/Kyiv")
_WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def _get_llm():
    global _LLM
    if _LLM is None:
        _LLM = build_llm()
    return _LLM


def _extract_text(ctx: RequestContext) -> str:
    if ctx.message is None:
        return ""
    out = []
    for p in ctx.message.parts or []:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None)
        if text:
            out.append(text)
    return "\n".join(out)


def _metadata_skill(ctx: RequestContext) -> str | None:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if not meta:
        return None
    sid = meta.get("skillId") if isinstance(meta, dict) else getattr(meta, "skillId", None)
    return sid if sid in SKILL_PROMPTS else None


def _params_from_metadata(ctx: RequestContext) -> dict:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if isinstance(meta, dict):
        extra = meta.get("params")
        return dict(extra) if isinstance(extra, dict) else {}
    return {}


async def _infer_skill_via_llm(message: str) -> str | None:
    known = ", ".join(SKILL_PROMPTS.keys())
    prompt = (
        "Pick exactly one skill ID for this user message. "
        f"Valid IDs: {known}. Respond with the ID only.\n\nMessage: {message}"
    )
    try:
        result = await _get_llm().ainvoke([HumanMessage(prompt)])
        raw = result.content if isinstance(result.content, str) else str(result.content)
    except Exception as e:
        logger.warning("LLM skill inference failed: %s", e)
        return None
    token = raw.strip().split()[0] if raw else ""
    return token if token in SKILL_PROMPTS else None


_JSON_BLOCK = re.compile(r"\{.*\}", re.DOTALL)


def _parse_json(raw: str) -> dict | None:
    if not raw:
        return None
    text = raw.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```\s*$", "", text)
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError:
        m = _JSON_BLOCK.search(text)
        if not m:
            return None
        try:
            parsed = json.loads(m.group(0))
        except json.JSONDecodeError:
            return None
    return parsed if isinstance(parsed, dict) else None


def _validate_define(parsed: dict) -> dict | None:
    """Return a validated kwargs dict for `registry.create`, or None if invalid."""
    if not isinstance(parsed, dict):
        return None
    name = (parsed.get("name") or "").strip().lower()
    kind = parsed.get("kind")
    cad_type = parsed.get("cadence_type")
    cad_days = parsed.get("cadence_days")
    target = parsed.get("target_value")
    unit = parsed.get("unit")
    if not name or kind not in ("boolean", "quantitative"):
        return None
    if cad_type not in ("daily", "weekly"):
        return None
    if cad_type == "weekly":
        if not isinstance(cad_days, list) or not cad_days:
            return None
        cad_days = [d for d in cad_days if d in _WEEKDAYS]
        if not cad_days:
            return None
    else:
        cad_days = None
    if kind == "quantitative":
        try:
            target = float(target) if target is not None else None
        except (TypeError, ValueError):
            target = None
    else:
        target, unit = None, None
    return {
        "name": name, "kind": kind, "cadence_type": cad_type,
        "cadence_days": cad_days, "target_value": target, "unit": unit,
    }


def _day_start_kyiv(dt: datetime) -> datetime:
    local = dt.astimezone(_DAY_TZ)
    return datetime(local.year, local.month, local.day, tzinfo=_DAY_TZ)


def _weekday_short(dt: datetime) -> str:
    return _WEEKDAYS[dt.astimezone(_DAY_TZ).weekday()]


def _expected_today(habit: dict, today_local: datetime) -> bool:
    if habit["cadence_type"] == "daily":
        return True
    days = habit.get("cadence_days") or []
    return _WEEKDAYS[today_local.weekday()] in days


def _day_complete(habit: dict, day_rows: list[dict]) -> bool:
    if not day_rows:
        return False
    if habit["kind"] == "boolean":
        return any(r.get("completed") for r in day_rows)
    total = 0.0
    for r in day_rows:
        v = r.get("value")
        if v is None:
            continue
        try:
            total += float(v)
        except (TypeError, ValueError):
            continue
    target = habit.get("target_value") or 0
    return total >= float(target) if target > 0 else total > 0


def _current_streak(habit: dict, rows_by_day: dict[str, list[dict]], today: datetime) -> int:
    streak = 0
    cursor = today
    for _ in range(400):  # sane cap
        key = cursor.date().isoformat()
        if habit["cadence_type"] == "weekly":
            if _WEEKDAYS[cursor.weekday()] not in (habit.get("cadence_days") or []):
                cursor -= timedelta(days=1)
                continue
        if _day_complete(habit, rows_by_day.get(key, [])):
            streak += 1
            cursor -= timedelta(days=1)
        else:
            break
    return streak


def _group_by_day(rows: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in rows:
        day = _day_start_kyiv(r["recorded_at"]).date().isoformat()
        d = r.get("data") or {}
        out.setdefault(day, []).append(d)
    return out


async def _build_streak_summary() -> str:
    habits = await registry.list_active()
    if not habits:
        return ""
    logs = await fetch_habit_logs(days=60)
    rows_by_habit: dict[str, list[dict]] = {}
    for r in logs:
        hid = (r.get("data") or {}).get("habit_id")
        if hid:
            rows_by_habit.setdefault(hid, []).append(r)

    today = datetime.now(_DAY_TZ)
    parts: list[str] = []
    for h in habits:
        rows = rows_by_habit.get(h["id"], [])
        by_day = _group_by_day(rows)
        streak = _current_streak(h, by_day, today)
        today_rows = by_day.get(today.date().isoformat(), [])
        done_today = _day_complete(h, today_rows)
        marker = "✅" if done_today else "⬜"
        bit = f"{marker} {h['name']} {streak}d"
        if h["kind"] == "quantitative" and h.get("target_value") is not None:
            total = 0.0
            for r in today_rows:
                try:
                    total += float(r.get("value") or 0)
                except (TypeError, ValueError):
                    continue
            bit += f" ({int(total)}/{int(h['target_value'])}{h.get('unit') or ''})"
        parts.append(bit)
    return " · ".join(parts)


def _clip_summary(text: str) -> str:
    cleaned = (text or "").strip()
    if len(cleaned) <= _LOG_ENTRY_SUMMARY_MAX:
        return cleaned
    return cleaned[:_LOG_ENTRY_SUMMARY_MAX - 1] + "…"


class HabitsAgentExecutor(AgentExecutor):
    async def execute(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        task_id = ctx.task_id or str(uuid.uuid4())
        context_id = ctx.context_id or str(uuid.uuid4())
        message = _extract_text(ctx)
        skill_id = _metadata_skill(ctx) or await _infer_skill_via_llm(message)

        await _emit_status(event_queue, task_id, context_id, TaskState.working)

        if skill_id is None or skill_id not in SKILL_PROMPTS:
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error="cannot determine skill", final=True,
            )
            return

        try:
            params = _params_from_metadata(ctx)
            params.setdefault("message", message)
            output = ""

            if skill_id == "define_habit":
                prompt = await SKILL_PROMPTS[skill_id](message, params)
                result = await _get_llm().ainvoke([HumanMessage(prompt)])
                raw = result.content if isinstance(result.content, str) else str(result.content)
                parsed = _parse_json(raw)
                validated = _validate_define(parsed) if parsed else None
                if validated is None:
                    output = "couldn't parse definition, try more precisely"
                else:
                    try:
                        habit_id = await registry.create(**validated)
                        output = (
                            f"tracking '{validated['name']}' ({validated['kind']}, "
                            f"{validated['cadence_type']}) id={habit_id}"
                        )
                    except Exception as e:
                        output = f"habit '{validated['name']}' already tracked"
                        logger.warning("registry.create failed: %s", e)

            elif skill_id == "log_habit_check":
                habit_id = params.get("habit_id")
                habit: dict | None = None
                if habit_id:
                    habits = await registry.list_active()
                    habit = next((h for h in habits if h["id"] == habit_id), None)
                else:
                    name = params.get("name") or message
                    habit = await registry.find_by_name(name)
                if habit is None:
                    output = ("habit not found — `/habits` lists active ones, "
                              "`/habit new ...` creates one")
                else:
                    value = params.get("value")
                    unit = params.get("unit") or habit.get("unit")
                    note = params.get("note")
                    data = {
                        "habit_id": habit["id"],
                        "name": habit["name"],
                        "completed": True,
                        "raw_text": message,
                        "source_skill": "log_habit_check",
                    }
                    if value is not None:
                        try:
                            data["value"] = float(value)
                        except (TypeError, ValueError):
                            pass
                    if unit:
                        data["unit"] = unit
                    if note:
                        data["note"] = note
                    await insert_log(
                        agent="habits", type_="habit",
                        data=data, source=params.get("source", "telegram"),
                    )
                    val_bit = f" ({data.get('value')}{data.get('unit','')})" if "value" in data else ""
                    output = f"checked '{habit['name']}'{val_bit}"
                    await _emit_log_entry_artifact(event_queue, task_id, context_id, message)

            elif skill_id == "analyze_habit":
                prompt = await SKILL_PROMPTS[skill_id](message, params)
                result = await _get_llm().ainvoke([HumanMessage(prompt)])
                output = result.content if isinstance(result.content, str) else str(result.content)

            elif skill_id == "get_streak_summary":
                summary = await _build_streak_summary()
                output = summary or "no active habits"

            elif skill_id == "archive_habit":
                habit_id = params.get("habit_id")
                if not habit_id:
                    name = params.get("name") or message
                    habit = await registry.find_by_name(name)
                    habit_id = habit["id"] if habit else None
                if not habit_id:
                    output = "habit not found"
                else:
                    ok = await registry.archive(habit_id)
                    output = "archived" if ok else "already archived"

            await insert_task_record(
                agent="habits", task_id=task_id, context_id=context_id,
                skill_id=skill_id, input_=params, output=output, state="completed",
            )
            try:
                await upsert_memory(
                    agent_id="habits",
                    id_=str(uuid.uuid4()),
                    text=message if skill_id == "log_habit_check" else output,
                    metadata={
                        "skill": skill_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                logger.warning("upsert_memory failed: %s", e)

            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("habits executor failed")
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error=str(e), final=True,
            )

    async def cancel(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        await _emit_status(event_queue, ctx.task_id, ctx.context_id, TaskState.canceled, final=True)


def _error_message(text: str) -> Message:
    return Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text=text))],
        message_id=str(uuid.uuid4()),
    )


async def _emit_status(event_queue: EventQueue, task_id: str, context_id: str,
                       state: TaskState, error: str | None = None, final: bool = False) -> None:
    status = TaskStatus(state=state)
    if error:
        status.message = _error_message(error)
    await event_queue.enqueue_event(TaskStatusUpdateEvent(
        task_id=task_id, context_id=context_id, status=status, final=final,
    ))


async def _emit_artifact(event_queue: EventQueue, task_id: str, context_id: str,
                         name: str, text: str) -> None:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name=name,
        parts=[Part(root=TextPart(text=text))],
    )
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=task_id, context_id=context_id, artifact=artifact,
        append=False, last_chunk=True,
    ))


async def _emit_log_entry_artifact(
    event_queue: EventQueue,
    task_id: str,
    context_id: str,
    raw_message: str,
) -> None:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name="log_entry",
        parts=[Part(root=DataPart(data={
            "summary": _clip_summary(raw_message),
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))],
    )
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=task_id, context_id=context_id, artifact=artifact,
        append=False, last_chunk=True,
    ))
