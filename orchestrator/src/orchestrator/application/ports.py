from __future__ import annotations

from collections.abc import AsyncGenerator, Mapping, Sequence
from contextlib import AbstractAsyncContextManager
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any, Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.a2a.proposals import Proposal

from orchestrator.domain.attachments import Upload
from orchestrator.domain.tasks import task_key

ActionStatus = Literal["pending", "applying", "applied", "rejected", "expired", "failed"]


@dataclass(frozen=True, slots=True)
class ChatTask:
    id: UUID
    user_id: UUID
    household_id: UUID | None
    lead_agent: str | None
    title: str | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True, slots=True)
class NewMessage:
    role: Literal["user", "assistant"]
    text: str
    agent: str | None = None
    consulted: Sequence[str] = ()
    attachments: Sequence[Mapping[str, Any]] = ()
    action: Mapping[str, Any] | None = None


@dataclass(frozen=True, slots=True)
class TranscriptMessage:
    seq: int
    role: str
    text: str
    agent: str | None
    consulted: tuple[str, ...]
    attachments: tuple[Mapping[str, Any], ...]
    action: Mapping[str, Any] | None
    created_at: datetime


@dataclass(frozen=True, slots=True)
class PendingAction:
    id: UUID
    task_id: UUID
    household_id: UUID | None
    agent: str
    kind: str
    payload: Mapping[str, Any]
    summary: str
    status: ActionStatus
    result_code: str | None
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class Claim:
    action: PendingAction | None
    reason: Literal["claimed", "rejected", "already_decided", "expired", "not_found"]


class ChatTaskRepository(Protocol):
    async def create(
        self, user_id: UUID, *, lead_agent: str | None, title: str | None, household_id: UUID | None
    ) -> ChatTask: ...
    async def get(self, user_id: UUID, task_id: UUID) -> ChatTask | None: ...
    async def list(self, user_id: UUID, limit: int = 50) -> list[ChatTask]: ...
    async def update(
        self, user_id: UUID, task_id: UUID, changes: Mapping[str, object]
    ) -> ChatTask | None:
        """changes ⊆ {lead_agent, title, household_id}; a key present with None clears it."""
        ...

    async def touch(self, user_id: UUID, task_id: UUID) -> None: ...
    async def delete(self, user_id: UUID, task_id: UUID) -> bool:
        """Deletes the task, its messages and pending actions (cascade). Checkpoints are separate."""
        ...


class TranscriptRepository(Protocol):
    async def append(self, user_id: UUID, task_id: UUID, message: NewMessage) -> int:
        """Next seq for the task (1-based); concurrent appends to one task never collide."""
        ...

    async def list(self, user_id: UUID, task_id: UUID) -> list[TranscriptMessage]: ...
    async def set_action_status(
        self, user_id: UUID, task_id: UUID, action_id: UUID, status: str
    ) -> None: ...


class PendingActionRepository(Protocol):
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
        """Expires the task's previous pending action in the same transaction."""
        ...

    async def pending(self, user_id: UUID, task_id: UUID) -> PendingAction | None:
        """The task's pending, unexpired action (expiry by the database clock)."""
        ...

    async def claim(
        self, user_id: UUID, task_id: UUID, action_id: UUID, decision: Literal["confirm", "reject"]
    ) -> Claim:
        """Atomically move pending → applying (confirm) or → rejected (reject); expired → 'expired'."""
        ...

    async def finish(
        self,
        user_id: UUID,
        action_id: UUID,
        status: Literal["applied", "failed"],
        result_code: str | None,
    ) -> None: ...


@dataclass(frozen=True, slots=True)
class RunContext:
    user_id: UUID
    task_id: UUID
    household_id: UUID | None
    lead_agent: str | None
    zone: ZoneInfo
    locale: str
    now: datetime

    @property
    def key(self) -> str:
        return task_key(self.user_id, self.task_id)


@dataclass(frozen=True, slots=True)
class ToolDone:
    agent: str
    consulted: tuple[str, ...] = ()
    proposal_id: UUID | None = None
    failed: bool = False


@dataclass(frozen=True, slots=True)
class FinalText:
    text: str


GraphEvent = ToolDone | FinalText


class TaskBusy(Exception):
    """Another run holds this task."""


class InvalidHistory(Exception):
    """The stored conversation cannot be continued (an interrupted tool call)."""


class GraphSession(Protocol):
    def run(self, text: str) -> AsyncGenerator[GraphEvent, None]: ...
    async def append(self, user_text: str, assistant_text: str) -> None: ...
    async def reset(self) -> None: ...


class ChatGraph(Protocol):
    def session(
        self, ctx: RunContext, last_user_text: str
    ) -> AbstractAsyncContextManager[GraphSession]: ...


@dataclass(frozen=True, slots=True)
class PeerReply:
    text: str
    consulted: tuple[str, ...] = ()
    data: Mapping[str, Any] | None = None
    failed: bool = False


class PeerUnavailable(Exception):
    pass


class PeerAgents(Protocol):
    async def ask(
        self,
        agent: str,
        *,
        user_id: UUID,
        skill: str,
        text: str,
        focus_sources: Sequence[str] | None,
    ) -> PeerReply: ...


class VisionUnavailable(Exception):
    pass


class ImageDescriber(Protocol):
    async def describe(self, image: Upload, question: str, locale: str) -> str: ...


class UnreadableDocument(Exception):
    pass


class DocumentReader(Protocol):
    def text(self, data: bytes) -> str: ...


class SyncUnavailable(Exception):
    pass


class HealthSync(Protocol):
    async def sync_user(self, user_id: UUID) -> list[Mapping[str, object]]: ...


class ProposalRecorder(Protocol):
    async def record(self, ctx: RunContext, agent: str, proposal: Proposal) -> PendingAction: ...


class HouseholdLookup(Protocol):
    async def current(self, user_id: UUID) -> UUID | None: ...


class ConsentLookup(Protocol):
    async def bodies_ok(self, user_id: UUID) -> bool: ...
