"""In-memory twins of the chat repositories (same contract as adapters/db.py; see tests/contract)."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import replace
from datetime import timedelta
from typing import Any, Literal
from uuid import UUID, uuid4

from shared.a2a.proposals import Proposal
from shared.ports.clock import Clock
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import InMemoryUnitOfWorkFactory, InMemoryUserSettings

from orchestrator.application.ports import (
    ChatTask,
    ChatTaskRepository,
    Claim,
    NewMessage,
    PeerReply,
    PendingAction,
    PendingActionRepository,
    RunContext,
    SyncUnavailable,
    TranscriptMessage,
    TranscriptRepository,
)


class InMemoryChatTasks:
    def __init__(self, clock: Clock) -> None:
        self._clock = clock
        self.rows: dict[UUID, ChatTask] = {}
        self.on_delete: list[
            Callable[[UUID], object]
        ] = []  # the transcript and actions register cascades here

    async def create(
        self, user_id: UUID, *, lead_agent: str | None, title: str | None, household_id: UUID | None
    ) -> ChatTask:
        now = self._clock.now()
        task = ChatTask(uuid4(), user_id, household_id, lead_agent, title, now, now)
        self.rows[task.id] = task
        return task

    async def get(self, user_id: UUID, task_id: UUID) -> ChatTask | None:
        task = self.rows.get(task_id)
        return task if task and task.user_id == user_id else None

    async def list(self, user_id: UUID, limit: int = 50) -> list[ChatTask]:
        mine = [t for t in self.rows.values() if t.user_id == user_id]
        return sorted(mine, key=lambda t: t.updated_at, reverse=True)[:limit]

    async def update(
        self, user_id: UUID, task_id: UUID, changes: Mapping[str, object]
    ) -> ChatTask | None:
        task = await self.get(user_id, task_id)
        if task is None:
            return None
        allowed = {k: v for k, v in changes.items() if k in ("lead_agent", "title", "household_id")}
        updated = replace(task, **allowed, updated_at=self._clock.now())  # type: ignore[arg-type]
        self.rows[task_id] = updated
        return updated

    async def touch(self, user_id: UUID, task_id: UUID) -> None:
        if (task := await self.get(user_id, task_id)) is not None:
            self.rows[task_id] = replace(task, updated_at=self._clock.now())

    async def delete(self, user_id: UUID, task_id: UUID) -> bool:
        if await self.get(user_id, task_id) is None:
            return False
        del self.rows[task_id]
        for cascade in self.on_delete:
            cascade(task_id)
        return True


class InMemoryTranscript:
    def __init__(self, tasks: InMemoryChatTasks, clock: Clock) -> None:
        self._tasks, self._clock = tasks, clock
        self.rows: dict[UUID, list[TranscriptMessage]] = {}
        tasks.on_delete.append(lambda task_id: self.rows.pop(task_id, None))

    async def append(self, user_id: UUID, task_id: UUID, message: NewMessage) -> int:
        if await self._tasks.get(user_id, task_id) is None:
            raise LookupError("task")
        rows = self.rows.setdefault(task_id, [])
        seq = len(rows) + 1
        rows.append(
            TranscriptMessage(
                seq,
                message.role,
                message.text,
                message.agent,
                tuple(message.consulted),
                tuple(dict(a) for a in message.attachments),
                dict(message.action) if message.action is not None else None,
                self._clock.now(),
            )
        )
        return seq

    async def list(self, user_id: UUID, task_id: UUID) -> list[TranscriptMessage]:
        return list(self.rows.get(task_id, [])) if await self._tasks.get(user_id, task_id) else []

    async def set_action_status(
        self, user_id: UUID, task_id: UUID, action_id: UUID, status: str
    ) -> None:
        if await self._tasks.get(user_id, task_id) is None:
            return
        rows = self.rows.get(task_id, [])
        for i, m in enumerate(rows):
            if m.action and m.action.get("id") == str(action_id):
                rows[i] = replace(m, action={**m.action, "status": status})


class InMemoryPendingActions:
    def __init__(self, tasks: InMemoryChatTasks, clock: Clock) -> None:
        self._tasks, self._clock = tasks, clock
        self.rows: dict[UUID, tuple[UUID, PendingAction]] = {}  # id → (user, action)
        tasks.on_delete.append(
            lambda task_id: [
                self.rows.pop(k) for k, (_, a) in list(self.rows.items()) if a.task_id == task_id
            ]
        )

    def _set(self, action: PendingAction, **changes: object) -> PendingAction:
        user = self.rows[action.id][0]
        updated = replace(action, **changes)  # type: ignore[arg-type]
        self.rows[action.id] = (user, updated)
        return updated

    async def propose(
        self,
        user_id: UUID,
        task_id: UUID,
        *,
        agent: str,
        kind: str,
        payload: Mapping[str, Any],
        summary: str,
        household_id: UUID | None,
        ttl: timedelta,
    ) -> PendingAction:
        if await self._tasks.get(user_id, task_id) is None:
            raise LookupError("task")
        for _, action in [
            v
            for v in self.rows.values()
            if v[0] == user_id and v[1].task_id == task_id and v[1].status == "pending"
        ]:
            self._set(action, status="expired")
        action = PendingAction(
            uuid4(),
            task_id,
            household_id,
            agent,
            kind,
            dict(payload),
            summary,
            "pending",
            None,
            self._clock.now() + ttl,
        )
        self.rows[action.id] = (user_id, action)
        return action

    async def pending(self, user_id: UUID, task_id: UUID) -> PendingAction | None:
        now = self._clock.now()
        return next(
            (
                a
                for u, a in self.rows.values()
                if u == user_id
                and a.task_id == task_id
                and a.status == "pending"
                and a.expires_at > now
            ),
            None,
        )

    async def claim(
        self, user_id: UUID, task_id: UUID, action_id: UUID, decision: Literal["confirm", "reject"]
    ) -> Claim:
        entry = self.rows.get(action_id)
        if entry is None or entry[0] != user_id or entry[1].task_id != task_id:
            return Claim(None, "not_found")
        action = entry[1]
        if action.status != "pending":
            return Claim(action, "expired" if action.status == "expired" else "already_decided")
        if action.expires_at <= self._clock.now():
            return Claim(self._set(action, status="expired"), "expired")
        if decision == "reject":
            return Claim(self._set(action, status="rejected"), "rejected")
        return Claim(self._set(action, status="applying"), "claimed")

    async def finish(
        self,
        user_id: UUID,
        action_id: UUID,
        status: Literal["applied", "failed"],
        result_code: str | None,
    ) -> None:
        entry = self.rows.get(action_id)
        if entry and entry[0] == user_id and entry[1].status == "applying":
            self._set(entry[1], status=status, result_code=result_code)


def in_memory_uow(
    clock: Clock, settings: InMemoryUserSettings | None = None
) -> InMemoryUnitOfWorkFactory:
    tasks = InMemoryChatTasks(clock)
    return InMemoryUnitOfWorkFactory(
        {
            ChatTaskRepository: tasks,
            TranscriptRepository: InMemoryTranscript(tasks, clock),
            PendingActionRepository: InMemoryPendingActions(tasks, clock),
            UserSettingsRepository: settings or InMemoryUserSettings(),
        }
    )


class FakePeerAgents:
    def __init__(self, replies: dict[str, PeerReply | Exception] | None = None) -> None:
        self.replies = replies or {}
        self.calls: list[tuple[str, UUID, str, str, list[str] | None]] = []

    async def ask(
        self,
        agent: str,
        *,
        user_id: UUID,
        skill: str,
        text: str,
        focus_sources: Sequence[str] | None,
    ) -> PeerReply:
        self.calls.append(
            (agent, user_id, skill, text, list(focus_sources) if focus_sources else None)
        )
        reply = self.replies.get(agent, PeerReply(f"{agent} reply"))
        if isinstance(reply, Exception):
            raise reply
        return reply


class RecordedProposals:
    def __init__(self) -> None:
        self.recorded: list[tuple[str, Proposal]] = []
        self.actions: list[PendingAction] = []

    async def record(self, ctx: RunContext, agent: str, proposal: Proposal) -> PendingAction:
        action = PendingAction(
            uuid4(),
            ctx.task_id,
            None,
            agent,
            proposal.action,
            dict(proposal.payload),
            proposal.summary,
            "pending",
            None,
            ctx.now + timedelta(minutes=5),
        )
        self.recorded.append((agent, proposal))
        self.actions.append(action)
        return action


class FakeHealthSync:
    def __init__(
        self, results: list[dict[str, object]] | None = None, *, down: bool = False
    ) -> None:
        self.results, self.down = results or [], down
        self.users: list[UUID] = []

    async def sync_user(self, user_id: UUID) -> list[Mapping[str, object]]:
        self.users.append(user_id)
        if self.down:
            raise SyncUnavailable
        return list(self.results)
