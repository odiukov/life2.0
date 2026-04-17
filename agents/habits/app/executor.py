"""Habits agent executor — filled out in Task 6."""
from __future__ import annotations

import uuid

from a2a.server.agent_execution import AgentExecutor, RequestContext
from a2a.server.events import EventQueue
from a2a.types import TaskState, TaskStatus, TaskStatusUpdateEvent


class HabitsAgentExecutor(AgentExecutor):
    async def execute(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        task_id = ctx.task_id or str(uuid.uuid4())
        context_id = ctx.context_id or str(uuid.uuid4())
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.failed),
            final=True,
        ))

    async def cancel(self, ctx: RequestContext, event_queue: EventQueue) -> None:
        task_id = ctx.task_id or str(uuid.uuid4())
        context_id = ctx.context_id or str(uuid.uuid4())
        await event_queue.enqueue_event(TaskStatusUpdateEvent(
            task_id=task_id,
            context_id=context_id,
            status=TaskStatus(state=TaskState.canceled),
            final=True,
        ))
