"""SleepAgentExecutor — maps incoming A2A messages to sleep-domain skills."""
from __future__ import annotations

import asyncio
import json
import logging
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

from shared.claude_runner import run_claude
from shared.peer import fetch_peer_artifacts
from shared.vector import upsert_memory
from shared.db import insert_task_record

from .skills import PEER_SKILLS, SKILL_PROMPTS

logger = logging.getLogger(__name__)

_WORKOUT_KEYWORDS = {
    "тренировк", "трениров", "workout", "exercise", "нагрузк", "training",
    "физ", "спорт", "sport", "run", "бег", "кардио", "cardio",
}
_NUTRITION_KEYWORDS = {
    "питани", "еда", "еде", "калори", "nutrition", "food", "calorie",
    "protein", "белок", "алкогол", "alcohol", "кофе", "coffee",
    "ужин", "dinner", "поздн", "late",
}


def _decide_peers(skill_id: str, message: str) -> set[str]:
    if skill_id == "log_sleep":
        return set()
    if skill_id == "get_sleep_recommendations":
        return {"workout"}
    if skill_id != "analyze_sleep":
        return set()
    low = message.lower()
    needed: set[str] = set()
    if any(k in low for k in _WORKOUT_KEYWORDS):
        needed.add("workout")
    if any(k in low for k in _NUTRITION_KEYWORDS):
        needed.add("nutrition")
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
    """Fallback when the caller didn't provide metadata.skillId.

    We ask Claude to pick one of the known skills; on failure returns None.
    """
    known = ", ".join(SKILL_PROMPTS.keys())
    prompt = (
        "You must pick exactly one skill ID that matches this user message. "
        f"Valid IDs: {known}. Respond with the skill ID only, no punctuation, no explanation.\n\n"
        f"User message: {message}"
    )
    try:
        raw = await asyncio.to_thread(run_claude, prompt, 30)
    except Exception as e:
        logger.warning("LLM skill inference failed: %s", e)
        return None
    cleaned = raw.strip().split()[0] if raw else ""
    return cleaned if cleaned in SKILL_PROMPTS else None


class SleepAgentExecutor(AgentExecutor):
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
            peer_agents = _peer_agents_from_metadata(ctx)
            needed = _decide_peers(skill_id, message)
            peer_artifacts = await fetch_peer_artifacts(peer_agents, PEER_SKILLS, needed=needed)
            params = _params_from_metadata(ctx)
            params.setdefault("message", message)
            params["peer_artifacts"] = peer_artifacts
            prompt_fn = SKILL_PROMPTS[skill_id]
            prompt = await prompt_fn(message, params)
            output = await asyncio.to_thread(run_claude, prompt)

            if skill_id != "briefing":
                await insert_task_record(
                    agent="sleep", task_id=task_id, context_id=context_id,
                    skill_id=skill_id, input_=params, output=output, state="completed",
                )
                await upsert_memory(
                    agent_id="sleep",
                    id_=str(uuid.uuid4()),
                    text=output,
                    metadata={
                        "skill": skill_id,
                        "params": json.dumps(
                            {k: v for k, v in params.items() if k != "peer_artifacts"}
                        ),
                    },
                )

            if skill_id.startswith("log_"):
                await _emit_log_entry_artifact(event_queue, task_id, context_id, message)
            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("sleep executor failed")
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error=str(e), final=True,
            )

    async def cancel(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        # TODO: cancel() just enqueues a canceled status; it does NOT kill the running
        # Claude subprocess (which runs in asyncio.to_thread). Properly killing it would
        # require refactoring shared/claude_runner.py to return the Popen handle.
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
    summary: str,
) -> None:
    artifact = Artifact(
        artifact_id=str(uuid.uuid4()),
        name="log_entry",
        parts=[Part(root=DataPart(data={
            "summary": summary[:120],
            "timestamp": datetime.now(timezone.utc).isoformat(),
        }))],
    )
    evt = TaskArtifactUpdateEvent(
        task_id=task_id,
        context_id=context_id,
        artifact=artifact,
        append=True,
        last_chunk=False,
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
