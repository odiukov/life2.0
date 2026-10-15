from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.ports.uow import UnitOfWorkFactory

from orchestrator.application.ports import (
    ChatGraph,
    ChatTask,
    ChatTaskRepository,
    GraphSession,
    HouseholdLookup,
    PendingAction,
    PendingActionRepository,
    RunContext,
    TranscriptMessage,
    TranscriptRepository,
)
from orchestrator.domain.catalog import CATALOG, LEAD_AGENTS
from orchestrator.domain.tasks import title_from

T = TypeVar("T")


class TaskNotFound(Exception):
    pass


class UnknownAgent(Exception):
    pass


class NoHousehold(Exception):
    pass


@dataclass(frozen=True, slots=True)
class TaskView:
    task: ChatTask
    messages: list[TranscriptMessage]
    pending: PendingAction | None


class Tasks:
    def __init__(
        self, *, uow: UnitOfWorkFactory, households: HouseholdLookup, graph: ChatGraph
    ) -> None:
        self._uow, self._households, self._graph = uow, households, graph

    async def _household_for(self, user_id: UUID, lead: str | None) -> UUID | None:
        if lead is None or not CATALOG[lead].household_scoped:
            return None
        household = await self._households.current(user_id)
        if household is None:
            raise NoHousehold
        return household

    def _check(self, lead: str | None) -> None:
        if lead is not None and lead not in LEAD_AGENTS:
            raise UnknownAgent(lead)

    async def open(self, user_id: UUID, *, lead_agent: str | None, title: str | None) -> ChatTask:
        self._check(lead_agent)
        household = await self._household_for(user_id, lead_agent)
        async with self._uow.for_user(user_id) as tx:
            return await tx.repo(ChatTaskRepository).create(
                user_id,
                lead_agent=lead_agent,
                title=title_from(title) if title else None,
                household_id=household,
            )

    async def list(self, user_id: UUID) -> list[ChatTask]:
        async with self._uow.for_user(user_id) as tx:
            return await tx.repo(ChatTaskRepository).list(user_id)

    async def read(self, user_id: UUID, task_id: UUID) -> TaskView:
        async with self._uow.for_user(user_id) as tx:
            task = await tx.repo(ChatTaskRepository).get(user_id, task_id)
            if task is None:
                raise TaskNotFound
            return TaskView(
                task,
                await tx.repo(TranscriptRepository).list(user_id, task_id),
                await tx.repo(PendingActionRepository).pending(user_id, task_id),
            )

    async def update(self, user_id: UUID, task_id: UUID, changes: Mapping[str, object]) -> ChatTask:
        await self.read(user_id, task_id)
        values = {k: v for k, v in changes.items() if k in ("lead_agent", "title")}
        if "lead_agent" in values:
            lead = values["lead_agent"]
            self._check(lead if isinstance(lead, str) else None)
            values["household_id"] = await self._household_for(
                user_id, lead if isinstance(lead, str) else None
            )
        if isinstance(values.get("title"), str):
            values["title"] = title_from(str(values["title"]))
        async with self._uow.for_user(user_id) as tx:
            task = await tx.repo(ChatTaskRepository).update(user_id, task_id, values)
        if task is None:
            raise TaskNotFound
        return task

    def _session(self, task: ChatTask) -> AbstractAsyncContextManager[GraphSession]:
        # Only reset()/append() run on this session; they need no clock, zone or locale.
        ctx = RunContext(
            task.user_id,
            task.id,
            task.household_id,
            task.lead_agent,
            ZoneInfo("UTC"),
            "en",
            datetime.now(UTC),
        )
        return self._graph.session(ctx, "")

    async def with_session(
        self, user_id: UUID, task: ChatTask, fn: Callable[[GraphSession], Awaitable[T]]
    ) -> T:
        """Run fn under the task's lock (TaskBusy while a reply is streaming)."""
        if task.user_id != user_id:
            raise TaskNotFound
        async with self._session(task) as session:
            await self.read(user_id, task.id)
            return await fn(session)

    async def close(self, user_id: UUID, task_id: UUID) -> None:
        task = (await self.read(user_id, task_id)).task
        async with self._session(task), self._uow.for_user(user_id) as tx:
            if not await tx.repo(ChatTaskRepository).delete(user_id, task_id):
                raise TaskNotFound
