"""NutritionAgentExecutor — maps incoming A2A messages to nutrition-domain skills."""
from __future__ import annotations

import json
import logging
import os
import uuid

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

_SYNC_SKILLS = {"analyze_nutrition", "get_nutrition_recommendations"}

# Skills that are handled as direct DB writes without an LLM call.
_DIRECT_SKILLS = {"set_body_profile"}

_VALID_SEX = {"male", "female"}
_VALID_ACTIVITY = {"sedentary", "light", "moderate", "active", "very_active"}


async def _execute_set_body_profile(uid, params: dict) -> str:
    """Extract body profile fields from the user message via LLM, validate, write to DB."""
    from shared.db import save_body_profile

    message = params.get("message", "")

    # Try to extract structured fields via LLM from the raw user message.
    extraction_prompt = (
        "Extract body profile fields from this user message and return ONLY a JSON object "
        "with any of these keys that are mentioned (omit keys not mentioned):\n"
        '  "height_cm" (number), "age" (integer), "sex" ("male" or "female"), '
        '  "activity_level" (one of: sedentary, light, moderate, active, very_active), '
        '  "calorie_goal_override" (integer kcal)\n\n'
        f"User message: {message}\n\n"
        "Return only valid JSON, no markdown, no explanation."
    )
    try:
        result = await _get_llm().ainvoke([HumanMessage(extraction_prompt)])
        raw_json = result.content if isinstance(result.content, str) else str(result.content)
        # Strip markdown code fences if present
        raw_json = raw_json.strip()
        if raw_json.startswith("```"):
            raw_json = raw_json.split("```")[1]
            if raw_json.startswith("json"):
                raw_json = raw_json[4:]
        extracted: dict = json.loads(raw_json.strip())
    except Exception as exc:
        logger.warning("set_body_profile: LLM extraction failed: %s", exc)
        extracted = {}

    # Merge extracted fields with any explicitly-provided params (params take priority).
    for key in ("height_cm", "age", "sex", "activity_level", "calorie_goal_override"):
        if key in params and params[key] is not None:
            extracted[key] = params[key]

    updates: dict = {}
    errors: list[str] = []

    height_cm = extracted.get("height_cm")
    if height_cm is not None:
        try:
            updates["height_cm"] = float(height_cm)
        except (TypeError, ValueError):
            errors.append(f"height_cm must be a number, got {height_cm!r}")

    age = extracted.get("age")
    if age is not None:
        try:
            updates["age"] = int(age)
        except (TypeError, ValueError):
            errors.append(f"age must be an integer, got {age!r}")

    sex = extracted.get("sex")
    if sex is not None:
        if sex not in _VALID_SEX:
            errors.append(f"sex must be one of {sorted(_VALID_SEX)}, got {sex!r}")
        else:
            updates["sex"] = sex

    activity_level = extracted.get("activity_level")
    if activity_level is not None:
        if activity_level not in _VALID_ACTIVITY:
            errors.append(
                f"activity_level must be one of {sorted(_VALID_ACTIVITY)}, got {activity_level!r}"
            )
        else:
            updates["activity_level"] = activity_level

    calorie_goal_override = extracted.get("calorie_goal_override")
    if calorie_goal_override is not None:
        try:
            updates["calorie_goal_override"] = int(calorie_goal_override)
        except (TypeError, ValueError):
            errors.append(
                f"calorie_goal_override must be an integer, got {calorie_goal_override!r}"
            )

    if errors:
        return "Body profile not saved — validation errors:\n" + "\n".join(f"• {e}" for e in errors)
    if not updates:
        return (
            "I couldn't find any body profile fields in your message. "
            "Please provide at least one of: height (cm), age, sex (male/female), "
            "activity level (sedentary/light/moderate/active/very_active), "
            "or a calorie goal (kcal)."
        )

    await save_body_profile(uid, updates)
    field_list = ", ".join(f"{k}={v}" for k, v in updates.items())
    return (
        f"Body profile updated: {field_list}. "
        "Your calorie goal will be recalculated on the next dashboard refresh."
    )


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


class NutritionAgentExecutor(AgentExecutor):
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
            params = _params_from_metadata(ctx)
            params["user_id"] = str(uid)
            params.setdefault("message", message)
            for_date = _for_date_from_metadata(metadata)
            if for_date:
                params["for_date"] = for_date

            # Direct DB skills bypass the LLM entirely.
            if skill_id in _DIRECT_SKILLS:
                output = await _execute_set_body_profile(uid, params)
                await insert_task_record(
                    agent="nutrition", task_id=task_id, context_id=context_id,
                    skill_id=skill_id, input_=params, output=output, state="completed",
                )
                await emit_consulted_peers_artifact(
                    event_queue, task_id, context_id, []
                )
                await _emit_artifact(event_queue, task_id, context_id, "analysis", output)
                await _emit_status(event_queue, task_id, context_id, TaskState.completed, final=True)
                return

            if skill_id in _SYNC_SKILLS:
                await _trigger_yazio_sync()

            # Depth-1 cap: when this nutrition call was issued by another agent
            # via call_peer(), do not consult any further peers — return only
            # nutrition-domain analysis.
            peer_artifacts: dict[str, str] = {}
            if not is_peer_call_from_metadata(metadata):
                peer_artifacts = await fetch_peer_artifacts(
                    default_peer_registry(),
                    PEER_SKILLS,
                    needed=set(consult),
                    user_id=str(uid),
                )
            params["peer_artifacts"] = peer_artifacts
            prompt_fn = SKILL_PROMPTS[skill_id]
            prompt = await prompt_fn(message, params)
            result = await _get_llm().ainvoke([HumanMessage(prompt)])
            output = result.content if isinstance(result.content, str) else str(result.content)

            await insert_task_record(
                agent="nutrition", task_id=task_id, context_id=context_id,
                skill_id=skill_id, input_=params, output=output, state="completed",
            )
            await upsert_memory(user_id=uid,
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
            await emit_consulted_peers_artifact(
                event_queue, task_id, context_id, list(peer_artifacts.keys())
            )
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
