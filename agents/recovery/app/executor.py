"""RecoveryAgentExecutor — maps incoming A2A messages to recovery-domain skills.

All three skills use the LLM for the final text; the bucket + deltas are
computed deterministically in shared.recovery and handed to the LLM as part
of the prompt snapshot.
"""
from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact, Message, Part, Role, TaskArtifactUpdateEvent,
    TaskState, TaskStatus, TaskStatusUpdateEvent, TextPart,
)
from langchain_core.messages import HumanMessage

from shared.consulted import emit_consulted_peers_artifact
from shared.current_user import user_id_from_message
from shared.db import insert_task_record
from shared.intent import infer_skill_and_consults
from shared.llm import build_llm
from shared.peer import (
    default_peer_registry, fetch_peer_artifacts,
    is_peer_call_from_metadata,
)
from shared.vector import upsert_memory

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


class RecoveryAgentExecutor(AgentExecutor):
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
            uid = await user_id_from_message(ctx.message)
            # Depth-1 cap: when this recovery call was issued by another agent
            # via call_peer(), do not consult further peers — return only
            # recovery-domain analysis.
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
            params["peer_artifacts"] = peer_artifacts
            prompt = await SKILL_PROMPTS[skill_id](message, params)
            result = await _get_llm().ainvoke([HumanMessage(prompt)])
            output = result.content if isinstance(result.content, str) else str(result.content)

            try:
                await insert_task_record(
                    agent="recovery", task_id=task_id, context_id=context_id,
                    skill_id=skill_id, input_=params, output=output, state="completed",
                )
            except Exception as e:
                logger.warning("insert_task_record failed: %s", e)
            try:
                await upsert_memory(user_id=uid,
                    agent_id="recovery",
                    id_=str(uuid.uuid4()),
                    text=output,
                    metadata={
                        "skill": skill_id,
                        "timestamp": datetime.now(timezone.utc).isoformat(),
                    },
                )
            except Exception as e:
                logger.warning("upsert_memory failed: %s", e)

            await emit_consulted_peers_artifact(
                event_queue, task_id, context_id, list(peer_artifacts.keys())
            )
            await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
            await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)

        except Exception as e:
            logger.exception("recovery executor failed")
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
