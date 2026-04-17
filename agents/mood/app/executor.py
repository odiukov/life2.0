"""MoodAgentExecutor — dispatches to mood skills and persists entries."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

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

from shared.db import insert_log, insert_task_record
from shared.llm import build_llm
from shared.vector import upsert_memory

from .skills import SKILL_PROMPTS

_LLM = None
logger = logging.getLogger(__name__)

_LOG_ENTRY_SUMMARY_MAX = 120


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


def _parse_mood_json(raw: str) -> dict | None:
    """Return a validated mood dict or None if parsing fails."""
    if not raw:
        return None
    # Tolerate minor LLM formatting slips (fenced blocks, leading text).
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
    if not isinstance(parsed, dict):
        return None
    return parsed


def _coerce_int(v, lo: int = 1, hi: int = 10) -> int | None:
    if v is None:
        return None
    try:
        n = int(v)
    except (TypeError, ValueError):
        return None
    if n < lo or n > hi:
        return None
    return n


def _coerce_valence(v) -> str | None:
    if v in ("pos", "neu", "neg"):
        return v
    return None


def _coerce_tags(v) -> list[str]:
    if not isinstance(v, list):
        return []
    out = []
    for t in v[:6]:
        if isinstance(t, str):
            cleaned = t.strip().lower()
            if cleaned:
                out.append(cleaned)
    return out


def _build_mood_data(raw_text: str, parsed: dict | None, source_skill: str) -> dict:
    if parsed is None:
        return {
            "mood_score": None,
            "energy": None,
            "stress": None,
            "valence": None,
            "tags": [],
            "raw_text": raw_text,
            "source_skill": "log_mood_fallback",
        }
    return {
        "mood_score": _coerce_int(parsed.get("mood_score")),
        "energy": _coerce_int(parsed.get("energy")),
        "stress": _coerce_int(parsed.get("stress")),
        "valence": _coerce_valence(parsed.get("valence")),
        "tags": _coerce_tags(parsed.get("tags")),
        "raw_text": raw_text,
        "source_skill": source_skill,
    }


def _clip_summary(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) <= _LOG_ENTRY_SUMMARY_MAX:
        return cleaned
    return cleaned[:_LOG_ENTRY_SUMMARY_MAX - 1] + "…"


class MoodAgentExecutor(AgentExecutor):
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
            prompt = await SKILL_PROMPTS[skill_id](message, params)
            result = await _get_llm().ainvoke([HumanMessage(prompt)])
            output = result.content if isinstance(result.content, str) else str(result.content)

            if skill_id == "log_mood":
                parsed = _parse_mood_json(output)
                source_skill = params.get("source_skill") or "log_mood"
                if parsed is None:
                    source_skill = "log_mood_fallback"
                data = _build_mood_data(message, parsed, source_skill)
                await insert_log(
                    agent="mood",
                    type_="mood",
                    data=data,
                    source=params.get("source", "telegram"),
                )
                human_reply = data.get("tags") or []
                score = data.get("mood_score")
                output = (
                    f"recorded mood ({score or '—'}/10), tags: {', '.join(human_reply) or 'none'}"
                )

            elif skill_id == "coach_session":
                # Optional entry point for direct A2A callers (not the default path
                # used by telegram). params may contain a session transcript + summary.
                data = _build_mood_data(
                    raw_text=params.get("transcript", message),
                    parsed=_parse_mood_json(output),
                    source_skill="coach_session",
                )
                await insert_log(
                    agent="mood",
                    type_="mood",
                    data=data,
                    source=params.get("source", "mood_agent"),
                )

            await insert_task_record(
                agent="mood", task_id=task_id, context_id=context_id,
                skill_id=skill_id, input_=params, output=output, state="completed",
            )
            try:
                await upsert_memory(
                    agent_id="mood",
                    id_=str(uuid.uuid4()),
                    text=message if skill_id == "log_mood" else output,
                    metadata={
                        "skill": skill_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                logger.warning("upsert_memory failed: %s", e)

            if skill_id == "log_mood":
                await _emit_log_entry_artifact(event_queue, task_id, context_id, message)

            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("mood executor failed")
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
