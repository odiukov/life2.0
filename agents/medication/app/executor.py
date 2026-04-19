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
from shared.llm import build_llm
from shared.vector import upsert_memory

from . import registry
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


class MedicationAgentExecutor(AgentExecutor):
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
                        mid = await registry.create(**validated)
                        dose_part = f" {validated['dose']}" if validated['dose'] else ""
                        output = f"tracking '{validated['name']}'{dose_part} · {validated['schedule']} id={mid}"
                    except Exception as e:
                        output = f"medication '{validated['name']}' already tracked"
                        logger.warning("registry.create failed: %s", e)

            elif skill_id == "log_taken":
                name = params.get("name") or message
                med = await registry.find_by_name(name)
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
                        "source_skill": "log_taken",
                    }
                    await insert_log(
                        agent="medication", type_="medication_taken",
                        data=data, source=params.get("source", "telegram"),
                    )
                    dose_bit = f" ({data['dose_at_time']})" if data["dose_at_time"] else ""
                    output = f"taken '{med['name']}'{dose_bit}"

            elif skill_id == "list_active":
                meds = await registry.list_active()
                if not meds:
                    output = "no active medications"
                else:
                    parts = []
                    for m in meds:
                        dose = f" {m['dose']}" if m.get("dose") else ""
                        parts.append(f"• {m['name']}{dose} · {m['schedule']}")
                    output = "\n".join(parts)

            elif skill_id == "archive_medication":
                name = params.get("name") or message
                med = await registry.find_by_name(name)
                if med is None:
                    output = "medication not found"
                else:
                    ok = await registry.archive(med["id"])
                    output = "archived" if ok else "already archived"

            elif skill_id == "analyze_adherence":
                window_days = int(params.get("window_days", 14))
                meds = await registry.list_active()
                if not meds:
                    output = "no active medications to analyse"
                else:
                    logs = await fetch_medication_logs(days=window_days)
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
                    prompt_text = await SKILL_PROMPTS[skill_id](
                        message,
                        {**params, "window_days": window_days,
                         "data": json.dumps(summary_rows, ensure_ascii=False)},
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
                await upsert_memory(
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
