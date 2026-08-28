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
from shared.current_user import user_id_from_message
from shared.intent import infer_skill_and_consults
from shared.llm import build_llm
from shared.peer import (
    default_peer_registry, fetch_peer_artifacts,
    is_peer_call_from_metadata,
)
from shared.vector import upsert_memory
from shared.consulted import emit_consulted_peers_artifact
from shared.log_entry import make_log_entry_artifact

from .skills import PEER_SKILLS, SKILL_PROMPTS

_LLM = None
logger = logging.getLogger(__name__)


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


def _metadata_dict(ctx: RequestContext) -> dict | None:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if isinstance(meta, dict):
        return meta
    if meta is None:
        return None
    return {
        "skillId": getattr(meta, "skillId", None),
        "focus_sources": getattr(meta, "focus_sources", None),
        "is_peer_call": getattr(meta, "is_peer_call", None),
    }


def _params_from_metadata(ctx: RequestContext) -> dict:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if isinstance(meta, dict):
        extra = meta.get("params")
        return dict(extra) if isinstance(extra, dict) else {}
    return {}


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


class MoodAgentExecutor(AgentExecutor):
    async def execute(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        task_id = ctx.task_id or str(uuid.uuid4())
        context_id = ctx.context_id or str(uuid.uuid4())
        message = _extract_text(ctx)
        metadata = _metadata_dict(ctx)
        skill_id, consult = await infer_skill_and_consults(
            message=message,
            skills=list(SKILL_PROMPTS.keys()),
            candidate_peers=list(PEER_SKILLS.keys()),
            metadata=metadata,
            llm=_get_llm(),
        )

        await _emit_status(event_queue, task_id, context_id, TaskState.working)

        if skill_id is None or skill_id not in SKILL_PROMPTS:
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error="cannot determine skill", final=True,
            )
            return

        try:
            user_id = await user_id_from_message(ctx.message)
            params = _params_from_metadata(ctx)
            params["user_id"] = str(user_id)
            params.setdefault("message", message)

            peer_artifacts: dict[str, str] = {}
            if (
                skill_id in {"analyze_mood", "get_mood_recommendations"}
                and not is_peer_call_from_metadata(metadata)
            ):
                peer_artifacts = await fetch_peer_artifacts(
                    default_peer_registry(),
                    PEER_SKILLS,
                    needed=set(consult),
                    user_id=str(user_id),
                )
            params["peer_artifacts"] = peer_artifacts

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
                    user_id,
                    agent="mood",
                    type_="mood",
                    data=data,
                    source=params.get("source", "manual"),
                )
                human_reply = data.get("tags") or []
                score = data.get("mood_score")
                output = (
                    f"recorded mood ({score or '—'}/10), tags: {', '.join(human_reply) or 'none'}"
                )

            elif skill_id == "coach_session":
                # Optional entry point for direct A2A callers (not the default chat-coach
                # path). params may contain a session transcript + summary.
                data = _build_mood_data(
                    raw_text=params.get("transcript", message),
                    parsed=_parse_mood_json(output),
                    source_skill="coach_session",
                )
                await insert_log(
                    user_id,
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
                await upsert_memory(user_id=user_id,
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

            await emit_consulted_peers_artifact(
                event_queue, task_id, context_id, list(peer_artifacts.keys())
            )
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
    artifact = make_log_entry_artifact(raw_message)
    evt = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=artifact,
        append=False,
        last_chunk=True,
    )
    await event_queue.enqueue_event(evt)
