"""Chat repositories over Postgres; RLS scopes every row to the tenant."""

from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import timedelta
from typing import Any, Literal
from uuid import UUID

from shared.schema.tables import chat_messages, chat_tasks, pending_actions
from sqlalchemy import Row, func, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from orchestrator.application.ports import (
    ChatTask,
    ChatTaskRepository,
    Claim,
    NewMessage,
    PendingAction,
    PendingActionRepository,
    TranscriptMessage,
    TranscriptRepository,
)

T, M, P = chat_tasks.c, chat_messages.c, pending_actions.c


def _task(r: Row[Any]) -> ChatTask:
    return ChatTask(
        r.id, r.user_id, r.household_id, r.lead_agent, r.title, r.created_at, r.updated_at
    )


def _action(r: Row[Any]) -> PendingAction:
    return PendingAction(
        r.id,
        r.task_id,
        r.household_id,
        r.agent,
        r.kind,
        dict(r.payload),
        r.summary,
        r.status,
        r.result_code,
        r.expires_at,
    )


class SqlChatTasks:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(
        self, user_id: UUID, *, lead_agent: str | None, title: str | None, household_id: UUID | None
    ) -> ChatTask:
        row = (
            await self._conn.execute(
                insert(chat_tasks)
                .values(
                    user_id=user_id, lead_agent=lead_agent, title=title, household_id=household_id
                )
                .returning(*chat_tasks.c)
            )
        ).one()
        return _task(row)

    async def get(self, user_id: UUID, task_id: UUID) -> ChatTask | None:
        row = (
            await self._conn.execute(
                select(chat_tasks).where(T.id == task_id, T.user_id == user_id)
            )
        ).one_or_none()
        return _task(row) if row else None

    async def list(self, user_id: UUID, limit: int = 50) -> list[ChatTask]:
        rows = await self._conn.execute(
            select(chat_tasks)
            .where(T.user_id == user_id)
            .order_by(T.updated_at.desc())
            .limit(limit)
        )
        return [_task(r) for r in rows]

    async def update(
        self, user_id: UUID, task_id: UUID, changes: Mapping[str, object]
    ) -> ChatTask | None:
        values = {k: v for k, v in changes.items() if k in ("lead_agent", "title", "household_id")}
        statement = (
            update(chat_tasks)
            .where(T.id == task_id, T.user_id == user_id)
            .values(**values, updated_at=func.now())
            .returning(*chat_tasks.c)
        )
        row = (await self._conn.execute(statement)).one_or_none()
        return _task(row) if row else None

    async def touch(self, user_id: UUID, task_id: UUID) -> None:
        await self._conn.execute(
            update(chat_tasks)
            .where(T.id == task_id, T.user_id == user_id)
            .values(updated_at=func.now())
        )

    async def delete(self, user_id: UUID, task_id: UUID) -> bool:
        result = await self._conn.execute(
            chat_tasks.delete().where(T.id == task_id, T.user_id == user_id).returning(T.id)
        )
        return result.first() is not None


class SqlTranscript:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def append(self, user_id: UUID, task_id: UUID, message: NewMessage) -> int:
        # Lock the task row: concurrent appends to one task queue up instead of colliding on seq.
        task = await self._conn.execute(
            select(T.id).where(T.id == task_id, T.user_id == user_id).with_for_update()
        )
        if task.scalar_one_or_none() is None:
            raise LookupError("task")
        seq = (
            await self._conn.execute(
                select(func.coalesce(func.max(M.seq), 0) + 1).where(M.task_id == task_id)
            )
        ).scalar_one()
        await self._conn.execute(
            insert(chat_messages).values(
                task_id=task_id,
                seq=seq,
                user_id=user_id,
                role=message.role,
                text=message.text,
                agent=message.agent,
                consulted=list(message.consulted),
                attachments=[dict(a) for a in message.attachments],
                action=dict(message.action) if message.action is not None else None,
            )
        )
        return int(seq)

    async def list(self, user_id: UUID, task_id: UUID) -> list[TranscriptMessage]:
        rows = await self._conn.execute(
            select(chat_messages).where(M.task_id == task_id, M.user_id == user_id).order_by(M.seq)
        )
        return [
            TranscriptMessage(
                r.seq,
                r.role,
                r.text,
                r.agent,
                tuple(r.consulted or ()),
                tuple(r.attachments or ()),
                r.action,
                r.created_at,
            )
            for r in rows
        ]

    async def set_action_status(
        self, user_id: UUID, task_id: UUID, action_id: UUID, status: str
    ) -> None:
        await self._conn.execute(
            text(
                "UPDATE chat_messages SET action = jsonb_set(action, '{status}', to_jsonb(CAST(:status AS text))) "
                "WHERE task_id = :task AND user_id = :user AND action->>'id' = :id"
            ),
            {"status": status, "task": task_id, "user": user_id, "id": str(action_id)},
        )


class SqlPendingActions:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

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
        task = await self._conn.execute(
            select(T.id).where(T.id == task_id, T.user_id == user_id).with_for_update()
        )
        if task.scalar_one_or_none() is None:
            raise LookupError("task")
        await self._conn.execute(
            update(pending_actions)
            .where(P.task_id == task_id, P.user_id == user_id, P.status == "pending")
            .values(status="expired", decided_at=func.now())
        )
        row = (
            await self._conn.execute(
                insert(pending_actions)
                .values(
                    user_id=user_id,
                    task_id=task_id,
                    agent=agent,
                    kind=kind,
                    payload=dict(payload),
                    summary=summary,
                    household_id=household_id,
                    expires_at=func.now() + ttl,
                )
                .returning(*pending_actions.c)
            )
        ).one()
        return _action(row)

    async def pending(self, user_id: UUID, task_id: UUID) -> PendingAction | None:
        row = (
            await self._conn.execute(
                select(pending_actions).where(
                    P.task_id == task_id,
                    P.user_id == user_id,
                    P.status == "pending",
                    P.expires_at > func.clock_timestamp(),
                )
            )
        ).one_or_none()
        return _action(row) if row else None

    async def claim(
        self, user_id: UUID, task_id: UUID, action_id: UUID, decision: Literal["confirm", "reject"]
    ) -> Claim:
        target = "applying" if decision == "confirm" else "rejected"
        row = (
            await self._conn.execute(
                update(pending_actions)
                .where(
                    P.id == action_id,
                    P.task_id == task_id,
                    P.user_id == user_id,
                    P.status == "pending",
                    P.expires_at > func.clock_timestamp(),
                )
                .values(status=target, decided_at=func.now())
                .returning(*pending_actions.c)
            )
        ).one_or_none()
        if row is not None:
            return Claim(_action(row), "claimed" if decision == "confirm" else "rejected")
        expired = (
            await self._conn.execute(
                update(pending_actions)
                .where(
                    P.id == action_id,
                    P.task_id == task_id,
                    P.user_id == user_id,
                    P.status == "pending",
                    P.expires_at <= func.clock_timestamp(),
                )
                .values(status="expired", decided_at=func.clock_timestamp())
                .returning(*pending_actions.c)
            )
        ).one_or_none()
        if expired is not None:
            return Claim(_action(expired), "expired")
        current = (
            await self._conn.execute(
                select(pending_actions).where(
                    P.id == action_id, P.task_id == task_id, P.user_id == user_id
                )
            )
        ).one_or_none()
        if current is None:
            return Claim(None, "not_found")
        return Claim(
            _action(current), "expired" if current.status == "expired" else "already_decided"
        )

    async def finish(
        self,
        user_id: UUID,
        action_id: UUID,
        status: Literal["applied", "failed"],
        result_code: str | None,
    ) -> None:
        await self._conn.execute(
            update(pending_actions)
            .where(P.id == action_id, P.user_id == user_id, P.status == "applying")
            .values(status=status, result_code=result_code)
        )


def chat_repositories() -> dict[type[Any], Callable[[AsyncConnection], Any]]:
    return {
        ChatTaskRepository: SqlChatTasks,
        TranscriptRepository: SqlTranscript,
        PendingActionRepository: SqlPendingActions,
    }
