"""Kitchen repositories over Postgres; row-level security scopes everything to the household."""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, replace
from datetime import datetime
from typing import Any, cast
from uuid import UUID

from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.schema.tables import (
    household_members,
    households,
    kitchen_batches,
    kitchen_clarifications,
    kitchen_operation_groups,
    users,
)
from sqlalchemy import delete, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.engine import Row
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine, AsyncTransaction

from kitchen.application.errors import NoHousehold
from kitchen.application.ports import (
    BatchRepository,
    ClarificationRepository,
    HouseholdContext,
    HouseholdView,
    LoggedChange,
    OperationGroup,
    OperationLog,
    PendingClarification,
    UserLocales,
)
from kitchen.domain.model import Batch, Category, ExpirySource, Location, Source, Status, Unit

_LOCALES = {"ru", "en"}
_LOCK = text("SELECT public.household_lock(CAST(:household_id AS uuid))")
_CURRENT = text("SELECT public.current_household_id()")


@dataclass
class _HouseholdScope:
    transaction: AsyncTransaction | None
    captured: bool = False
    household_id: UUID | None = None


def _scope(conn: AsyncConnection) -> _HouseholdScope:
    # Connection.info follows the pooled driver connection, so bind this state to
    # the active transaction. A later UoW must never inherit an earlier actor's home.
    transaction = conn.get_transaction()
    scope = cast(_HouseholdScope | None, conn.info.get("kitchen_household_scope"))
    if scope is None or scope.transaction is not transaction:
        scope = _HouseholdScope(transaction)
        conn.info["kitchen_household_scope"] = scope
    return scope


def _values(batch: Batch) -> dict[str, object]:
    return {
        "name": batch.name,
        "display_name": batch.display_name,
        "category": batch.category.value,
        "quantity": batch.quantity,
        "unit": batch.unit.value,
        "location": batch.location.value,
        "status": batch.status.value,
        "opened": batch.opened,
        "opened_on": batch.opened_on,
        "added_at": batch.added_at,
        "added_by": batch.added_by,
        "expires_on": batch.expires_on,
        "expiry_source": batch.expiry_source.value,
        "next_check_on": batch.next_check_on,
        "source": batch.source.value,
    }


def _batch(row: Row[Any]) -> Batch:
    return Batch(
        id=row.id,
        name=row.name,
        display_name=row.display_name,
        category=Category(row.category),
        quantity=row.quantity,
        unit=Unit(row.unit),
        location=Location(row.location),
        status=Status(row.status),
        opened=row.opened,
        opened_on=row.opened_on,
        added_at=row.added_at,
        added_by=row.added_by,
        expires_on=row.expires_on,
        expiry_source=ExpirySource(row.expiry_source),
        next_check_on=row.next_check_on,
        source=Source(row.source),
    )


class SqlHouseholdView:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def current(self) -> HouseholdContext | None:
        household_id = (await self._conn.execute(_CURRENT)).scalar_one_or_none()
        scope = _scope(self._conn)
        if not scope.captured:
            scope.captured = True
            scope.household_id = household_id
        if household_id is None:
            return None
        row = (
            await self._conn.execute(
                select(households.c.id, households.c.timezone).where(
                    households.c.id == household_id
                )
            )
        ).one_or_none()
        if row is None:
            return None
        members = await self._conn.execute(
            select(household_members.c.user_id, household_members.c.display_name).where(
                household_members.c.household_id == household_id
            )
        )
        return HouseholdContext(row.id, row.timezone, {m.user_id: m.display_name for m in members})


class SqlBatchRepository:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def lock(self) -> None:
        scope = _scope(self._conn)
        if not scope.captured:
            await SqlHouseholdView(self._conn).current()
        if scope.household_id is None:
            raise NoHousehold
        await self._conn.execute(_LOCK, {"household_id": scope.household_id})
        # This is a fresh statement after the potentially blocking lock. Membership
        # transfers use the same lock and cannot move the actor until UoW exit.
        current = (await self._conn.execute(_CURRENT)).scalar_one_or_none()
        if current != scope.household_id:
            raise NoHousehold

    async def list_active(self) -> list[Batch]:
        rows = await self._conn.execute(
            select(kitchen_batches)
            .where(kitchen_batches.c.status == Status.ACTIVE.value)
            .order_by(
                kitchen_batches.c.expires_on, kitchen_batches.c.added_at, kitchen_batches.c.id
            )
        )
        return [_batch(r) for r in rows]

    async def get(self, batch_id: UUID) -> Batch | None:
        row = (
            await self._conn.execute(
                select(kitchen_batches).where(kitchen_batches.c.id == batch_id)
            )
        ).one_or_none()
        return _batch(row) if row else None

    async def add(self, batch: Batch, *, group_id: UUID) -> Batch:
        values = {**_values(batch), "last_group_id": group_id}
        if batch.id is not None:
            values["id"] = batch.id
        new_id = (
            await self._conn.execute(
                insert(kitchen_batches).values(**values).returning(kitchen_batches.c.id)
            )
        ).scalar_one()
        return replace(batch, id=new_id)

    async def save(self, batch: Batch, *, group_id: UUID) -> None:
        await self._conn.execute(
            update(kitchen_batches)
            .where(kitchen_batches.c.id == batch.pk)
            .values(**_values(batch), last_group_id=group_id)
        )

    async def delete(self, batch_id: UUID) -> None:
        await self._conn.execute(delete(kitchen_batches).where(kitchen_batches.c.id == batch_id))

    async def restore(self, batch: Batch) -> None:
        values = {**_values(batch), "last_group_id": None}
        statement = insert(kitchen_batches).values(id=batch.pk, **values)
        await self._conn.execute(
            statement.on_conflict_do_update(index_elements=[kitchen_batches.c.id], set_=values)
        )

    async def last_groups(self, batch_ids: Sequence[UUID]) -> dict[UUID, UUID | None]:
        if not batch_ids:
            return {}
        rows = await self._conn.execute(
            select(kitchen_batches.c.id, kitchen_batches.c.last_group_id).where(
                kitchen_batches.c.id.in_(list(batch_ids))
            )
        )
        return {r.id: r.last_group_id for r in rows}


def _group(row: Row[Any]) -> OperationGroup:
    return OperationGroup(
        id=row.id,
        user_id=row.user_id,
        created_at=row.created_at,
        source=row.source,
        changes=tuple(
            LoggedChange(c["op_type"], UUID(c["batch_id"]), c.get("before"), c["after"])
            for c in row.changes
        ),
        undone_at=row.undone_at,
    )


class SqlOperationLog:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def add(self, group: OperationGroup) -> None:
        await self._conn.execute(
            insert(kitchen_operation_groups).values(
                id=group.id,
                user_id=group.user_id,
                created_at=group.created_at,
                source=group.source,
                changes=[
                    {
                        "op_type": c.op_type,
                        "batch_id": str(c.batch_id),
                        "before": c.before,
                        "after": c.after,
                    }
                    for c in group.changes
                ],
            )
        )

    async def get(self, group_id: UUID) -> OperationGroup | None:
        row = (
            await self._conn.execute(
                select(kitchen_operation_groups).where(kitchen_operation_groups.c.id == group_id)
            )
        ).one_or_none()
        return _group(row) if row else None

    async def latest_for_user(self, user_id: UUID) -> OperationGroup | None:
        row = (
            await self._conn.execute(
                select(kitchen_operation_groups)
                .where(
                    kitchen_operation_groups.c.user_id == user_id,
                    kitchen_operation_groups.c.undone_at.is_(None),
                )
                .order_by(
                    kitchen_operation_groups.c.created_at.desc(),
                    kitchen_operation_groups.c.insertion_order.desc(),
                )
                .limit(1)
            )
        ).one_or_none()
        return _group(row) if row else None

    async def mark_undone(self, group_id: UUID, *, at: datetime, by: UUID) -> None:
        await self._conn.execute(
            update(kitchen_operation_groups)
            .where(kitchen_operation_groups.c.id == group_id)
            .values(undone_at=at, undone_by=by)
        )


class SqlClarifications:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID, *, now: datetime) -> PendingClarification | None:
        row = (
            await self._conn.execute(
                select(kitchen_clarifications.c.payload, kitchen_clarifications.c.expires_at).where(
                    kitchen_clarifications.c.user_id == user_id,
                    kitchen_clarifications.c.expires_at > now,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        p = row.payload
        return PendingClarification(
            p["text"], p["ref"], p["reason"], tuple(p["candidates"]), row.expires_at
        )

    async def put(self, user_id: UUID, pending: PendingClarification) -> None:
        payload = {
            "text": pending.text,
            "ref": pending.ref,
            "reason": pending.reason,
            "candidates": list(pending.candidates),
        }
        statement = insert(kitchen_clarifications).values(
            user_id=user_id, payload=payload, expires_at=pending.expires_at
        )
        await self._conn.execute(
            statement.on_conflict_do_update(
                index_elements=[
                    kitchen_clarifications.c.household_id,
                    kitchen_clarifications.c.user_id,
                ],
                set_={"payload": payload, "expires_at": pending.expires_at},
            )
        )

    async def delete(self, user_id: UUID) -> None:
        await self._conn.execute(
            delete(kitchen_clarifications).where(kitchen_clarifications.c.user_id == user_id)
        )


class SqlUserLocales:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def locale(self, user_id: UUID) -> str | None:
        prefs = (
            await self._conn.execute(select(users.c.preferences).where(users.c.id == user_id))
        ).scalar_one_or_none()
        value = prefs.get("locale") if isinstance(prefs, Mapping) else None
        return value if isinstance(value, str) and value in _LOCALES else None


def kitchen_uow(
    engine: AsyncEngine,
    *,
    extra: Mapping[type[Any], Callable[[AsyncConnection], Any]] | None = None,
) -> SqlUnitOfWorkFactory:
    return SqlUnitOfWorkFactory(
        engine,
        {
            HouseholdView: SqlHouseholdView,
            BatchRepository: SqlBatchRepository,
            OperationLog: SqlOperationLog,
            ClarificationRepository: SqlClarifications,
            UserLocales: SqlUserLocales,
            **(extra or {}),
        },
    )
