"""NutritionAgentExecutor — maps incoming A2A messages to nutrition-domain skills."""
from __future__ import annotations

import asyncio
import json
import logging
import os
import uuid
from datetime import datetime, timezone

import httpx

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
from shared.llm import build_llm
from shared.peer import fetch_peer_artifacts
from shared.vector import upsert_memory
from shared.db import insert_task_record

_LLM = None  # lazy-initialised on first LLM call; patched in tests


def _get_llm():
    global _LLM
    if _LLM is None:
        _LLM = build_llm()
    return _LLM

from .skills import PEER_SKILLS, SKILL_PROMPTS

logger = logging.getLogger(__name__)

# Summary shown in the LogEntry DataPart; kept short for the chat UI toast card.
_LOG_ENTRY_SUMMARY_MAX = 120


def _clip_summary(text: str) -> str:
    cleaned = text.strip()
    if len(cleaned) <= _LOG_ENTRY_SUMMARY_MAX:
        return cleaned
    return cleaned[:_LOG_ENTRY_SUMMARY_MAX - 1] + "…"


_SYNC_SKILLS = {"analyze_nutrition", "get_nutrition_recommendations"}


async def _trigger_yazio_sync() -> None:
    """Fire-and-forget sync before analysis so results reflect latest Yazio data.

    Failure is logged and swallowed — stale data is acceptable, a sync failure
    must not block the analysis path.
    """
    url = os.environ.get("SYNC_SERVICE_URL", "")
    if not url:
        return
    try:
        async with httpx.AsyncClient(timeout=5.0) as client:
            await client.post(f"{url}/sync/nutrition")
    except Exception as e:
        logger.warning("Yazio sync trigger failed: %s", e)


_WORKOUT_KEYWORDS = {
    "тренировк", "трениров", "workout", "exercise", "нагрузк", "training",
    "физ", "спорт", "sport", "run", "бег", "восстановлени", "recover",
}
_SLEEP_KEYWORDS = {
    "сон", "сна", "сну", "sleep", "усталост", "fatigue", "tired",
    "отдых", "rest", "hrv", "readiness", "восстановл",
}


def _decide_peers(skill_id: str, message: str) -> set[str]:
    if skill_id == "log_meal":
        return set()
    if skill_id == "get_nutrition_recommendations":
        return {"workout"}
    if skill_id != "analyze_nutrition":
        return set()
    low = message.lower()
    needed: set[str] = set()
    if any(k in low for k in _WORKOUT_KEYWORDS):
        needed.add("workout")
    if any(k in low for k in _SLEEP_KEYWORDS):
        needed.add("sleep")
    return needed


def _extract_text(ctx: RequestContext) -> str:
    message = ctx.message
    if message is None:
        return ""
    parts = []
    for p in message.parts or []:
        root = getattr(p, "root", p)
        text = getattr(root, "text", None)
        if text:
            parts.append(text)
    return "\n".join(parts)


def _metadata_skill(ctx: RequestContext) -> str | None:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if not meta:
        return None
    skill_id = meta.get("skillId") if isinstance(meta, dict) else getattr(meta, "skillId", None)
    return skill_id if skill_id in SKILL_PROMPTS else None


async def _infer_skill_via_llm(message: str) -> str | None:
    known = ", ".join(SKILL_PROMPTS.keys())
    prompt = (
        "You must pick exactly one skill ID that matches this user message. "
        f"Valid IDs: {known}. Respond with the skill ID only, no punctuation, no explanation.\n\n"
        f"User message: {message}"
    )
    try:
        result = await _get_llm().ainvoke([HumanMessage(prompt)])
        raw = result.content if isinstance(result.content, str) else str(result.content)
    except Exception as e:
        logger.warning("LLM skill inference failed: %s", e)
        return None
    cleaned = raw.strip().split()[0] if raw else ""
    return cleaned if cleaned in SKILL_PROMPTS else None


class NutritionAgentExecutor(AgentExecutor):
    async def execute(self, ctx: RequestContext, event_queue: EventQueue) -> None:  # noqa: D401
        task_id = ctx.task_id or str(uuid.uuid4())
        context_id = ctx.context_id or str(uuid.uuid4())
        message = _extract_text(ctx)
        skill_id = _metadata_skill(ctx)
        if skill_id is None:
            skill_id = await _infer_skill_via_llm(message)

        await _emit_status(event_queue, task_id, context_id, TaskState.working)

        if skill_id is None or skill_id not in SKILL_PROMPTS:
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error="cannot determine skill", final=True,
            )
            return

        try:
            if skill_id in _SYNC_SKILLS:
                await _trigger_yazio_sync()

            peer_agents = _peer_agents_from_metadata(ctx)
            needed = _decide_peers(skill_id, message)
            peer_artifacts = await fetch_peer_artifacts(peer_agents, PEER_SKILLS, needed=needed)
            params = _params_from_metadata(ctx)
            params.setdefault("message", message)
            params["peer_artifacts"] = peer_artifacts
            prompt_fn = SKILL_PROMPTS[skill_id]
            prompt = await prompt_fn(message, params)
            result = await _get_llm().ainvoke([HumanMessage(prompt)])
            output = result.content if isinstance(result.content, str) else str(result.content)

            if skill_id != "briefing":
                await insert_task_record(
                    agent="nutrition", task_id=task_id, context_id=context_id,
                    skill_id=skill_id, input_=params, output=output, state="completed",
                )
                await upsert_memory(
                    agent_id="nutrition",
                    id_=str(uuid.uuid4()),
                    text=output,
                    metadata={
                        "skill": skill_id,
                        "params": json.dumps(
                            {k: v for k, v in params.items() if k != "peer_artifacts"}
                        ),
                    },
                )

            # emit only after durable persistence (insert_task_record + upsert_memory) succeeded,
            # so a log_entry never reaches the UI for a record that wasn't saved.
            if skill_id.startswith("log_"):
                await _emit_log_entry_artifact(event_queue, task_id, context_id, message)
            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("nutrition executor failed")
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error=str(e), final=True,
            )

    async def cancel(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        # cancel() enqueues a canceled status; it does NOT abort an in-flight
        # LLM request. Proper cancellation would require threading a cancel
        # token through shared.llm.
        await _emit_status(event_queue, ctx.task_id, ctx.context_id, TaskState.canceled, final=True)


def _peer_agents_from_metadata(ctx: RequestContext) -> dict:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if isinstance(meta, dict):
        return meta.get("peer_agents") or {}
    return {}


def _params_from_metadata(ctx: RequestContext) -> dict:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if isinstance(meta, dict):
        extra = meta.get("params")
        return dict(extra) if isinstance(extra, dict) else {}
    return {}


def _error_message(text: str) -> Message:
    return Message(
        role=Role.agent,
        parts=[Part(root=TextPart(text=text))],
        message_id=str(uuid.uuid4()),
    )


async def _emit_status(
    event_queue: EventQueue,
    task_id: str,
    context_id: str,
    state: TaskState,
    error: str | None = None,
    final: bool = False,
) -> None:
    status = TaskStatus(state=state)
    if error:
        status.message = _error_message(error)
    evt = TaskStatusUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        status=status,
        final=final,
    )
    await event_queue.enqueue_event(evt)


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
    evt = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=artifact,
        append=False,
        last_chunk=True,
    )
    await event_queue.enqueue_event(evt)


async def _emit_artifact(
    event_queue: EventQueue,
    task_id: str,
    context_id: str,
    name: str,
    text: str,
) -> None:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name=name,
        parts=[Part(root=TextPart(text=text))],
    )
    evt = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=artifact,
        append=False,
        last_chunk=True,
    )
    await event_queue.enqueue_event(evt)
