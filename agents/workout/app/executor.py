"""WorkoutAgentExecutor — maps incoming A2A messages to workout-domain skills."""
from __future__ import annotations

import json
import logging
import uuid

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
from shared.peer import (
    default_peer_registry,
    fetch_peer_artifacts,
    is_peer_call_from_metadata,
)
from shared.intent import infer_skill_and_consults
from shared.vector import upsert_memory
from shared.current_user import user_id_from_message
from shared.db import insert_task_record
from shared.consulted import emit_consulted_peers_artifact
from shared.log_entry import make_log_entry_artifact

_LLM = None  # lazy-initialised on first LLM call; patched in tests


def _get_llm():
    global _LLM
    if _LLM is None:
        _LLM = build_llm()
    return _LLM

from .skills import PEER_SKILLS, SKILL_PROMPTS

logger = logging.getLogger(__name__)


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


def _metadata_dict(ctx: RequestContext) -> dict | None:
    meta = getattr(ctx.message, "metadata", None) if ctx.message else None
    if isinstance(meta, dict):
        return meta
    if meta is None:
        return None
    # A2A SDK sometimes hands us an object — coerce to dict where possible.
    return {
        "skillId": getattr(meta, "skillId", None),
        "focus_sources": getattr(meta, "focus_sources", None),
        "is_peer_call": getattr(meta, "is_peer_call", None),
        "for_date": getattr(meta, "for_date", None),
    }


def _for_date_from_metadata(metadata: dict | None) -> str | None:
    if not isinstance(metadata, dict):
        return None
    val = metadata.get("for_date")
    return val if isinstance(val, str) and val else None


class WorkoutAgentExecutor(AgentExecutor):
    async def execute(self, ctx: RequestContext, event_queue: EventQueue) -> None:  # noqa: D401
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
            uid = await user_id_from_message(ctx.message)
            # Depth-1 cap: when this workout call was issued by another agent
            # via call_peer(), do not consult any further peers — return only
            # workout-domain analysis.
            peer_artifacts: dict[str, str] = {}
            if not is_peer_call_from_metadata(metadata):
                peer_artifacts = await fetch_peer_artifacts(
                    default_peer_registry(),
                    PEER_SKILLS,
                    needed=set(consult),
                    user_id=str(uid),
                )
            params = _params_from_metadata(ctx)
            params["user_id"] = str(uid)
            params.setdefault("message", message)
            for_date = _for_date_from_metadata(metadata)
            if for_date:
                params["for_date"] = for_date
            params["peer_artifacts"] = peer_artifacts
            prompt_fn = SKILL_PROMPTS[skill_id]
            prompt = await prompt_fn(message, params)
            result = await _get_llm().ainvoke([HumanMessage(prompt)])
            output = result.content if isinstance(result.content, str) else str(result.content)

            await insert_task_record(
                agent="workout", task_id=task_id, context_id=context_id,
                skill_id=skill_id, input_=params, output=output, state="completed",
            )
            await upsert_memory(user_id=uid,
                agent_id="workout",
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
            await emit_consulted_peers_artifact(
                event_queue, task_id, context_id, list(peer_artifacts.keys())
            )
            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("workout executor failed")
            await _emit_status(
                event_queue, task_id, context_id, TaskState.failed,
                error=str(e), final=True,
            )

    async def cancel(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        # cancel() enqueues a canceled status; it does NOT abort an in-flight
        # LLM request. Proper cancellation would require threading a cancel
        # token through shared.llm.
        await _emit_status(event_queue, ctx.task_id, ctx.context_id, TaskState.canceled, final=True)


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
    artifact = make_log_entry_artifact(raw_message)
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
