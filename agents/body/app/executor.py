"""BodyAgentExecutor — maps incoming A2A messages to body-domain skills."""
from __future__ import annotations

import json
import logging
import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact, Message, Part, Role, TaskArtifactUpdateEvent,
    TaskState, TaskStatus, TaskStatusUpdateEvent, TextPart,
)
from langchain_core.messages import HumanMessage

from shared.llm import build_llm
from shared.vector import upsert_memory
from shared.db import insert_task_record

from .skills import SKILL_PROMPTS

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


class BodyAgentExecutor(AgentExecutor):
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

            await insert_task_record(
                agent="body", task_id=task_id, context_id=context_id,
                skill_id=skill_id, input_=params, output=output, state="completed",
            )
            await upsert_memory(
                agent_id="body",
                id_=str(uuid.uuid4()),
                text=output,
                metadata={"skill": skill_id, "params": json.dumps(params)},
            )

            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("body executor failed")
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
