"""In-memory implementations of every port, for unit tests."""

from __future__ import annotations

import asyncio
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from datetime import UTC, date, datetime, timedelta
from types import TracebackType
from typing import Any, Literal, Self, TypeVar, cast
from uuid import UUID

from pydantic import BaseModel, ValidationError

from shared.ports.llm import LLMInvalidOutput, LLMTask
from shared.ports.scheduler import Job
from shared.ports.vector_memory import Memory

SchemaT = TypeVar("SchemaT", bound=BaseModel)
RepoT = TypeVar("RepoT")


@dataclass(frozen=True, slots=True)
class LLMCall:
    kind: Literal["structured", "text"]
    task: LLMTask
    system: str
    user: str
    schema: type[BaseModel] | None


class FakeLLM:
    """Scripted LLM. Queue answers (or exceptions) per call kind, or pass a responder."""

    def __init__(self, *, responder: Callable[[LLMCall], object] | None = None) -> None:
        self._responder = responder
        self._structured: list[object] = []
        self._text: list[object] = []
        self.calls: list[LLMCall] = []

    def queue_structured(self, *items: object) -> None:
        self._structured.extend(items)

    def queue_text(self, *items: object) -> None:
        self._text.extend(items)

    async def structured(
        self, *, task: LLMTask, system: str, user: str, schema: type[SchemaT]
    ) -> SchemaT:
        item = self._next(LLMCall("structured", task, system, user, schema), self._structured)
        if isinstance(item, schema):
            return item
        data = item.model_dump() if isinstance(item, BaseModel) else item
        try:
            return schema.model_validate(data)
        except ValidationError as exc:
            raise LLMInvalidOutput(repr(data), str(exc)) from exc

    async def text(self, *, task: LLMTask, system: str, user: str) -> str:
        return str(self._next(LLMCall("text", task, system, user, None), self._text))

    def _next(self, call: LLMCall, queue: list[object]) -> object:
        self.calls.append(call)
        if queue:
            item = queue.pop(0)
        elif self._responder is not None:
            item = self._responder(call)
        else:
            raise AssertionError(f"no scripted {call.kind} answer for {call.user[:80]!r}")
        if isinstance(item, BaseException):
            raise item
        return item


class FixedClock:
    def __init__(self, now: datetime) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self._now = now.astimezone(UTC)

    def now(self) -> datetime:
        return self._now

    def set(self, now: datetime) -> None:
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("FixedClock needs a timezone-aware datetime")
        self._now = now.astimezone(UTC)

    def advance(self, **delta: float) -> None:
        self._now += timedelta(**delta)


class InMemoryVectorMemory:
    def __init__(self) -> None:
        self.items: list[tuple[UUID, str, str, Memory]] = []

    async def upsert(
        self, *, user_id: UUID, agent: str, key: str, text: str, metadata: Mapping[str, str]
    ) -> None:
        self.items = [
            item for item in self.items if (item[0], item[1], item[2]) != (user_id, agent, key)
        ]
        self.items.append((user_id, agent, key, Memory(text, agent, dict(metadata))))

    async def search(
        self, *, user_id: UUID, query: str, limit: int, agents: Sequence[str] | None = None
    ) -> list[Memory]:
        found = [
            memory
            for owner, agent, _key, memory in self.items
            if owner == user_id and (agents is None or agent in agents)
        ]
        return found[:limit]


class FakePeerClient:
    def __init__(self, answers: Mapping[str, str] | None = None) -> None:
        self.answers = dict(answers or {})
        self.calls: list[dict[str, Any]] = []

    async def fetch_artifacts(
        self, *, user_id: UUID, wanted: Mapping[str, str], for_date: date | None = None
    ) -> dict[str, str]:
        self.calls.append({"user_id": user_id, "wanted": dict(wanted), "for_date": for_date})
        return {name: self.answers[name] for name in wanted if name in self.answers}


class FakeTaskRecords:
    def __init__(self) -> None:
        self.rows: list[dict[str, object]] = []

    async def record(
        self,
        *,
        agent: str,
        task_id: str,
        context_id: str | None,
        skill_id: str,
        input_: Mapping[str, object],
        output: str,
        state: str,
    ) -> None:
        self.rows.append(
            {
                "agent": agent,
                "task_id": task_id,
                "context_id": context_id,
                "skill_id": skill_id,
                "input": dict(input_),
                "output": output,
                "state": state,
            }
        )


class FakeScheduler:
    def __init__(self) -> None:
        self.jobs: dict[str, tuple[Job, int, int, str]] = {}
        self.running = False

    def add_cron(self, job_id: str, func: Job, *, hour: int, minute: int, tz: str) -> None:
        self.jobs[job_id] = (func, hour, minute, tz)

    async def start(self) -> None:
        self.running = True

    async def shutdown(self) -> None:
        self.running = False

    async def run(self, job_id: str) -> None:
        await self.jobs[job_id][0]()


class FakeSpeechToText:
    def __init__(self, transcript: str = "") -> None:
        self.transcript = transcript
        self.calls: list[tuple[int, str, str | None]] = []

    async def transcribe(self, audio: bytes, *, mime: str, language: str | None) -> str:
        self.calls.append((len(audio), mime, language))
        return self.transcript


class _InMemoryUnitOfWork:
    def __init__(self, factory: InMemoryUnitOfWorkFactory, user_id: UUID | None) -> None:
        self._factory = factory
        self.user_id = user_id

    async def __aenter__(self) -> Self:
        await asyncio.sleep(0)
        return self

    async def __aexit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        target = self._factory.commits if exc_type is None else self._factory.rollbacks
        target.append(self.user_id)

    def repo(self, kind: type[RepoT]) -> RepoT:
        try:
            repo = self._factory.repositories[kind]
        except KeyError:
            raise LookupError(f"no repository registered for {kind.__name__}") from None
        return cast(RepoT, repo)


@dataclass
class InMemoryUnitOfWorkFactory:
    """Shares repositories across transactions and records transaction outcomes.

    This test fake does not undo repository mutations on rollback. Its counters record
    transaction boundaries only, so tests should not treat rollback as state restoration.
    """

    repositories: Mapping[type[Any], Any]
    commits: list[UUID | None] = field(default_factory=list)
    rollbacks: list[UUID | None] = field(default_factory=list)

    def for_user(self, user_id: UUID) -> _InMemoryUnitOfWork:
        return _InMemoryUnitOfWork(self, user_id)

    def system(self) -> _InMemoryUnitOfWork:
        return _InMemoryUnitOfWork(self, None)
