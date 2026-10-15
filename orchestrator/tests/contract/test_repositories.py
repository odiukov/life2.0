"""One contract for the chat repositories on memory and on Postgres."""

from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from orchestrator.adapters.db import chat_repositories
from orchestrator.application.ports import (
    ChatTaskRepository,
    NewMessage,
    PendingActionRepository,
    TranscriptRepository,
)
from orchestrator.testing import in_memory_uow
from shared.adapters.db.engine import create_engine
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.config import DatabaseSettings
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.fakes import FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

T0 = datetime(2026, 10, 14, 9, tzinfo=UTC)


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    new_user: Callable[[], Awaitable[UUID]]
    expire: Callable[[UUID], Awaitable[None]]
    later: Callable[[], Awaitable[None]]  # make the next write's timestamp strictly later

    async def user_and_task(self, lead: str | None = None) -> tuple[UUID, UUID]:
        user = await self.new_user()
        async with self.uow.for_user(user) as tx:
            task = await tx.repo(ChatTaskRepository).create(
                user, lead_agent=lead, title=None, household_id=None
            )
        return user, task.id


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    clock = FixedClock(T0)
    uow = in_memory_uow(clock)

    async def new_user() -> UUID:
        return uuid4()

    async def expire(action_id: UUID) -> None:
        clock.advance(minutes=6)

    async def later() -> None:
        clock.advance(seconds=1)

    yield Backend(uow, new_user, expire, later)


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    admin = create_async_engine(urls.admin)

    async def new_user() -> UUID:
        user = uuid4()
        async with admin.begin() as conn:
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": user})
        return user

    async def expire(action_id: UUID) -> None:
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "UPDATE pending_actions SET expires_at = now() - interval '1 minute' WHERE id = :i"
                ),
                {"i": action_id},
            )

    async def later() -> None:
        import asyncio

        await asyncio.sleep(0.01)

    try:
        yield Backend(SqlUnitOfWorkFactory(engine, chat_repositories()), new_user, expire, later)
    finally:
        await engine.dispose()
        await admin.dispose()


BACKENDS = {"memory": memory_backend, "sql": sql_backend}


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = BACKENDS[request.param](request)
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


def propose_args(**kw: object) -> dict[str, object]:
    return {
        "agent": "home",
        "kind": "home.call_tool",
        "payload": {"tool": "HassTurnOff"},
        "summary": "Turn off?",
        "household_id": None,
        "ttl": timedelta(minutes=5),
        **kw,
    }


async def test_tasks_crud_and_isolation(backend: Backend) -> None:
    user, first = await backend.user_and_task(lead="kitchen")
    await backend.later()
    async with backend.uow.for_user(user) as tx:
        second = await tx.repo(ChatTaskRepository).create(
            user, lead_agent=None, title="Plan", household_id=None
        )
    await backend.later()
    async with backend.uow.for_user(user) as tx:
        repo = tx.repo(ChatTaskRepository)
        await repo.touch(user, first)
        assert [t.id for t in await repo.list(user)] == [first, second.id]
        cleared = await repo.update(user, first, {"lead_agent": None})
        assert cleared is not None
        assert cleared.lead_agent is None
    other = await backend.new_user()
    async with backend.uow.for_user(other) as tx:
        repo = tx.repo(ChatTaskRepository)
        assert await repo.get(other, first) is None
        assert await repo.list(other) == []
        assert await repo.update(other, first, {"title": "x"}) is None
        assert await repo.delete(other, first) is False
    async with backend.uow.for_user(user) as tx:
        assert await tx.repo(ChatTaskRepository).delete(user, first) is True
        assert await tx.repo(ChatTaskRepository).delete(user, first) is False


async def test_transcript_seq_and_action_status(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    action_id = uuid4()
    async with backend.uow.for_user(user) as tx:
        log = tx.repo(TranscriptRepository)
        assert (
            await log.append(
                user,
                task,
                NewMessage(
                    "user",
                    "выключи свет",
                    attachments=[
                        {"kind": "image", "name": "a.jpg", "mime": "image/jpeg", "size": 10}
                    ],
                ),
            )
            == 1
        )
        assert (
            await log.append(
                user,
                task,
                NewMessage(
                    "assistant",
                    "Подтверди",
                    agent="home",
                    consulted=["kitchen"],
                    action={"id": str(action_id), "summary": "Turn off?", "status": "pending"},
                ),
            )
            == 2
        )
        await log.set_action_status(user, task, action_id, "applied")
        messages = await log.list(user, task)
    assert [m.seq for m in messages] == [1, 2]
    assert messages[0].attachments[0]["name"] == "a.jpg"
    assert messages[0].action is None
    assert messages[1].consulted == ("kitchen",)
    assert messages[1].action["status"] == "applied"


async def test_proposing_expires_the_previous_pending_action(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    async with backend.uow.for_user(user) as tx:
        repo = tx.repo(PendingActionRepository)
        first = await repo.propose(user, task, **propose_args())
        second = await repo.propose(user, task, **propose_args(summary="Turn on?"))
        current = await repo.pending(user, task)
        old = await repo.claim(user, task, first.id, "confirm")
    assert current is not None
    assert current.id == second.id
    assert old.reason == "expired"


async def test_double_confirm_claims_once(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    async with backend.uow.for_user(user) as tx:
        action = await tx.repo(PendingActionRepository).propose(user, task, **propose_args())
    async with backend.uow.for_user(user) as tx:
        first = await tx.repo(PendingActionRepository).claim(user, task, action.id, "confirm")
    async with backend.uow.for_user(user) as tx:
        second = await tx.repo(PendingActionRepository).claim(user, task, action.id, "confirm")
        await tx.repo(PendingActionRepository).finish(user, action.id, "applied", None)
        await tx.repo(PendingActionRepository).finish(
            user, action.id, "failed", "late"
        )  # no longer applying: ignored
    async with backend.uow.for_user(user) as tx:
        third = await tx.repo(PendingActionRepository).claim(user, task, action.id, "confirm")
    assert (first.reason, second.reason, third.reason) == (
        "claimed",
        "already_decided",
        "already_decided",
    )
    assert third.action is not None
    assert third.action.status == "applied"
    assert third.action.result_code is None


async def test_reject_then_confirm_is_already_decided(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    async with backend.uow.for_user(user) as tx:
        repo = tx.repo(PendingActionRepository)
        action = await repo.propose(user, task, **propose_args())
        rejected = await repo.claim(user, task, action.id, "reject")
        confirm = await repo.claim(user, task, action.id, "confirm")
    assert (rejected.reason, confirm.reason) == ("rejected", "already_decided")


async def test_expired_action_is_not_applied_even_when_confirmed(backend: Backend) -> None:
    """Review Focus 2: a card tapped after expiry must not run."""
    user, task = await backend.user_and_task()
    async with backend.uow.for_user(user) as tx:
        action = await tx.repo(PendingActionRepository).propose(user, task, **propose_args())
    await backend.expire(action.id)
    async with backend.uow.for_user(user) as tx:
        claim = await tx.repo(PendingActionRepository).claim(user, task, action.id, "confirm")
        pending = await tx.repo(PendingActionRepository).pending(user, task)
    assert claim.reason == "expired"
    assert pending is None
    async with backend.uow.for_user(user) as tx:
        again = await tx.repo(PendingActionRepository).claim(user, task, action.id, "confirm")
    assert again.reason == "expired"


async def test_other_users_cannot_see_or_claim(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    async with backend.uow.for_user(user) as tx:
        action = await tx.repo(PendingActionRepository).propose(user, task, **propose_args())
    other = await backend.new_user()
    async with backend.uow.for_user(other) as tx:
        assert await tx.repo(PendingActionRepository).pending(other, task) is None
        assert (
            await tx.repo(PendingActionRepository).claim(other, task, action.id, "confirm")
        ).reason == "not_found"
        assert await tx.repo(TranscriptRepository).list(other, task) == []


async def test_deleting_a_task_removes_its_messages_and_actions(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    async with backend.uow.for_user(user) as tx:
        await tx.repo(TranscriptRepository).append(user, task, NewMessage("user", "hi"))
        await tx.repo(PendingActionRepository).propose(user, task, **propose_args())
    async with backend.uow.for_user(user) as tx:
        assert await tx.repo(ChatTaskRepository).delete(user, task) is True
    async with backend.uow.for_user(user) as tx:
        assert await tx.repo(TranscriptRepository).list(user, task) == []
        assert await tx.repo(PendingActionRepository).pending(user, task) is None


async def test_other_user_cannot_modify_transcript_action(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    action_id = uuid4()
    async with backend.uow.for_user(user) as tx:
        await tx.repo(TranscriptRepository).append(
            user,
            task,
            NewMessage("assistant", "Confirm?", action={"id": str(action_id), "status": "pending"}),
        )
    other = await backend.new_user()
    async with backend.uow.for_user(other) as tx:
        await tx.repo(TranscriptRepository).set_action_status(other, task, action_id, "applied")
    async with backend.uow.for_user(user) as tx:
        messages = await tx.repo(TranscriptRepository).list(user, task)
    assert messages[0].action["status"] == "pending"


async def test_missing_or_foreign_task_rejects_children(backend: Backend) -> None:
    _, task = await backend.user_and_task()
    other = await backend.new_user()
    for task_id in (task, uuid4()):
        with pytest.raises(LookupError, match="task"):
            async with backend.uow.for_user(other) as tx:
                await tx.repo(TranscriptRepository).append(other, task_id, NewMessage("user", "hi"))
        with pytest.raises(LookupError, match="task"):
            async with backend.uow.for_user(other) as tx:
                await tx.repo(PendingActionRepository).propose(other, task_id, **propose_args())


async def test_expired_claim_returns_expired_status(backend: Backend) -> None:
    user, task = await backend.user_and_task()
    async with backend.uow.for_user(user) as tx:
        action = await tx.repo(PendingActionRepository).propose(user, task, **propose_args())
    await backend.expire(action.id)
    async with backend.uow.for_user(user) as tx:
        claim = await tx.repo(PendingActionRepository).claim(user, task, action.id, "confirm")
    assert claim.action is not None
    assert claim.action.status == "expired"


async def test_concurrent_appends_and_claims(backend: Backend) -> None:
    import asyncio

    user, task = await backend.user_and_task()

    async def append():
        async with backend.uow.for_user(user) as tx:
            return await tx.repo(TranscriptRepository).append(user, task, NewMessage("user", "hi"))

    assert sorted(await asyncio.gather(append(), append())) == [1, 2]
    async with backend.uow.for_user(user) as tx:
        action = await tx.repo(PendingActionRepository).propose(user, task, **propose_args())

    async def claim():
        async with backend.uow.for_user(user) as tx:
            return (
                await tx.repo(PendingActionRepository).claim(user, task, action.id, "confirm")
            ).reason

    assert sorted(await asyncio.gather(claim(), claim())) == ["already_decided", "claimed"]


async def test_concurrent_proposals_leave_one_pending(backend: Backend) -> None:
    import asyncio

    user, task = await backend.user_and_task()

    async def propose():
        async with backend.uow.for_user(user) as tx:
            return await tx.repo(PendingActionRepository).propose(user, task, **propose_args())

    actions = await asyncio.gather(propose(), propose())
    async with backend.uow.for_user(user) as tx:
        claims = [
            await tx.repo(PendingActionRepository).claim(user, task, a.id, "confirm")
            for a in actions
        ]
    assert sorted(c.reason for c in claims) == ["claimed", "expired"]
