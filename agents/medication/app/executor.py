"""MedicationAgentExecutor — dispatches medication skills."""
from __future__ import annotations

import json
import logging
import re
import uuid
from datetime import datetime, timezone

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import (
    Artifact, Message, Part, Role,
    TaskArtifactUpdateEvent, TaskState, TaskStatus, TaskStatusUpdateEvent,
    TextPart,
)
from langchain_core.messages import HumanMessage

from shared.db import insert_log, insert_task_record, fetch_medication_logs
from shared.current_user import user_id_from_message
from shared.intent import infer_skill_and_consults
from shared.log_entry import make_log_entry_artifact
from shared.peer import (
    default_peer_registry, fetch_peer_artifacts,
    is_peer_call_from_metadata,
)
from shared.skill_ids import Medication
from shared.llm import build_llm
from shared.vector import upsert_memory
from shared.consulted import emit_consulted_peers_artifact

from . import registry
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
    if not isinstance(parsed, dict):
        return None
    name = (parsed.get("name") or "").strip()
    schedule = (parsed.get("schedule") or "").strip()
    if not name or not schedule:
        return None
    dose = parsed.get("dose")
    notes = parsed.get("notes")
    return {
        "name": name,
        "dose": dose if isinstance(dose, str) and dose else None,
        "schedule": schedule,
        "notes": notes if isinstance(notes, str) and notes else None,
    }


async def _emit_log_entry(
    event_queue: EventQueue, task_id: str, context_id: str, summary: str,
) -> None:
    artifact = make_log_entry_artifact(summary)
    await event_queue.enqueue_event(TaskArtifactUpdateEvent(
        task_id=task_id, context_id=context_id, artifact=artifact,
        append=False, last_chunk=True,
    ))


class MedicationAgentExecutor(AgentExecutor):
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
            peer_artifacts: dict[str, str] = {}
            params.setdefault("message", message)
            output = ""

            if skill_id == "define_medication":
                prompt = await SKILL_PROMPTS[skill_id](message, params)
                result = await _get_llm().ainvoke([HumanMessage(prompt)])
                raw = result.content if isinstance(result.content, str) else str(result.content)
                parsed = _parse_json(raw)
                validated = _validate_define(parsed) if parsed else None
                if validated is None:
                    output = "couldn't parse definition, try more precisely"
                else:
                    try:
                        mid = await registry.create(user_id, **validated)
                        dose_part = f" {validated['dose']}" if validated['dose'] else ""
                        output = f"tracking '{validated['name']}'{dose_part} · {validated['schedule']} id={mid}"
                    except Exception as e:
                        output = f"medication '{validated['name']}' already tracked"
                        logger.warning("registry.create failed: %s", e)

            elif skill_id == Medication.LOG:
                name = params.get("name") or message
                med = await registry.find_by_name(user_id, name)
                if med is None:
                    output = (
                        "medication not found — `/med list` shows active ones, "
                        "`/med new ...` creates one"
                    )
                else:
                    data = {
                        "name": med["name"],
                        "medication_id": med["id"],
                        "dose_at_time": params.get("dose_override") or med.get("dose"),
                        "note": params.get("note"),
                        "raw_text": message,
                        "source_skill": Medication.LOG,
                    }
                    await insert_log(
                        user_id, agent="medication", type_="medication_taken",
                        data=data, source=params.get("source", "manual"),
                    )
                    dose_bit = f" ({data['dose_at_time']})" if data["dose_at_time"] else ""
                    output = f"taken '{med['name']}'{dose_bit}"
                    await _emit_log_entry(
                        event_queue, task_id, context_id,
                        f"Принял {med['name']}{dose_bit}",
                    )

            elif skill_id == "list_active":
                meds = await registry.list_active(user_id)
                if not meds:
                    output = "no active medications"
                else:
                    parts = []
                    for m in meds:
                        dose = f" {m['dose']}" if m.get("dose") else ""
                        parts.append(f"• {m['name']}{dose} · {m['schedule']}")
                    output = "\n".join(parts)

            elif skill_id == Medication.ARCHIVE:
                name = params.get("name") or message
                med = await registry.find_by_name(user_id, name)
                if med is None:
                    output = "medication not found"
                else:
                    ok = await registry.archive(user_id, med["id"])
                    output = "archived" if ok else "already archived"
                    if ok:
                        await _emit_log_entry(
                            event_queue, task_id, context_id,
                            f"Архивировано: {med['name']}",
                        )

            elif skill_id == "analyze_adherence":
                window_days = int(params.get("window_days", 14))
                meds = await registry.list_active(user_id)
                if not meds:
                    output = "no active medications to analyse"
                else:
                    logs = await fetch_medication_logs(user_id, days=window_days)
                    by_name: dict[str, int] = {}
                    for r in logs:
                        n = (r.get("data") or {}).get("name")
                        if n:
                            by_name[n] = by_name.get(n, 0) + 1
                    summary_rows = [
                        {"name": m["name"], "schedule": m["schedule"],
                         "actual_logs": by_name.get(m["name"], 0)}
                        for m in meds
                    ]
                    if not is_peer_call_from_metadata(metadata):
                        peer_artifacts = await fetch_peer_artifacts(
                            default_peer_registry(),
                            PEER_SKILLS,
                            needed=set(consult),
                            user_id=str(user_id),
                        )
                    prompt_text = await SKILL_PROMPTS[skill_id](
                        message,
                        {**params, "window_days": window_days,
                         "data": json.dumps(summary_rows, ensure_ascii=False),
                         "peer_artifacts": peer_artifacts},
                    )
                    result = await _get_llm().ainvoke([HumanMessage(prompt_text)])
                    output = result.content if isinstance(result.content, str) else str(result.content)

            else:
                output = f"skill '{skill_id}' not implemented yet"

            try:
                await insert_task_record(
                    agent="medication", task_id=task_id, context_id=context_id,
                    skill_id=skill_id, input_=params, output=output, state="completed",
                )
            except Exception as e:
                logger.warning("insert_task_record failed: %s", e)
            try:
                await upsert_memory(user_id=user_id,
                    agent_id="medication",
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
            logger.exception("medication executor failed")
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
