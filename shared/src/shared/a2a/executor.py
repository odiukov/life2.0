"""Base A2A executor: routing, statuses, artifacts and task records for every migrated agent."""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import datetime

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskState

from shared.a2a.events import (
    consulted_peers_event,
    log_entry_event,
    status_event,
    text_artifact_event,
)
from shared.a2a.request import (
    InvalidRequest,
    SkillRequest,
    focus_sources,
    read_envelope,
    requested_skill,
    to_request,
)
from shared.a2a.routing import resolve_skill
from shared.observability.logging import get_logger, logging_context
from shared.ports.clock import Clock
from shared.ports.llm import LLMProvider
from shared.ports.tasks import TaskRecords

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class SkillResult:
    output: str
    log_entry: str | None = None
    log_recorded_at: datetime | None = None
    consulted: tuple[str, ...] = ()


SkillHandler = Callable[[SkillRequest, tuple[str, ...]], Awaitable[SkillResult]]


class SkillExecutor(AgentExecutor):
    def __init__(
        self,
        *,
        agent: str,
        handlers: Mapping[str, SkillHandler],
        peers: Sequence[str],
        llm: LLMProvider,
        task_records: TaskRecords,
        clock: Clock,
    ) -> None:
        self._agent = agent
        self._handlers = dict(handlers)
        self._peers = list(peers)
        self._llm = llm
        self._task_records = task_records
        self._clock = clock

    async def execute(self, context: RequestContext, event_queue: EventQueue) -> None:
        envelope = read_envelope(context)
        task_id, context_id = envelope.task_id, envelope.context_id
        await event_queue.enqueue_event(status_event(task_id, context_id, TaskState.working))
        with logging_context(agent=self._agent, task_id=task_id):
            try:
                choice = await resolve_skill(
                    llm=self._llm,
                    message=envelope.text,
                    skills=list(self._handlers),
                    candidate_peers=self._peers,
                    requested_skill=requested_skill(envelope.metadata),
                    focus_sources=focus_sources(envelope.metadata),
                )
            except Exception:
                logger.exception("skill_failed")
                await event_queue.enqueue_event(
                    status_event(
                        task_id, context_id, TaskState.failed, error="internal error", final=True
                    )
                )
                return
        if choice is None:
            await event_queue.enqueue_event(
                status_event(
                    task_id,
                    context_id,
                    TaskState.failed,
                    error="cannot determine skill",
                    final=True,
                )
            )
            return
        with logging_context(agent=self._agent, skill_id=choice.skill_id, task_id=task_id):
            try:
                request = to_request(envelope, skill_id=choice.skill_id)
            except InvalidRequest as exc:
                await event_queue.enqueue_event(
                    status_event(task_id, context_id, TaskState.failed, error=str(exc), final=True)
                )
                return
            try:
                consult = () if request.is_peer_call else choice.consult
                result = await self._handlers[choice.skill_id](request, consult)
                await self._task_records.record(
                    agent=self._agent,
                    task_id=task_id,
                    context_id=context_id,
                    skill_id=choice.skill_id,
                    input_=request.audit(),
                    output=result.output,
                    state="completed",
                )
            except Exception:
                logger.exception("skill_failed")
                await event_queue.enqueue_event(
                    status_event(
                        task_id, context_id, TaskState.failed, error="internal error", final=True
                    )
                )
                return
            if result.log_entry is not None:
                recorded_at = result.log_recorded_at or self._clock.now()
                await event_queue.enqueue_event(
                    log_entry_event(task_id, context_id, result.log_entry, recorded_at)
                )
            await event_queue.enqueue_event(
                consulted_peers_event(task_id, context_id, result.consulted)
            )
            await event_queue.enqueue_event(
                text_artifact_event(task_id, context_id, "analysis", result.output)
            )
            await event_queue.enqueue_event(
                status_event(task_id, context_id, TaskState.completed, final=True)
            )
            logger.info("skill_completed")

    async def cancel(self, context: RequestContext, event_queue: EventQueue) -> None:
        # Enqueues a canceled status; it does not abort an in-flight LLM call (as before).
        envelope = read_envelope(context)
        await event_queue.enqueue_event(
            status_event(envelope.task_id, envelope.context_id, TaskState.canceled, final=True)
        )
