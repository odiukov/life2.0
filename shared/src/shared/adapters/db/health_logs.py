from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.ports.health_logs import HealthLogRow
from shared.schema.tables import health_logs

_ONE_US = timedelta(microseconds=1)
_MAX_SHIFTS = 1000


class SqlHealthLogs:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def recent(
        self,
        user_id: UUID,
        *,
        types: Sequence[str],
        limit: int | None = None,
        since: datetime | None = None,
        agent: str | None = None,
        data_equals: Mapping[str, str] | None = None,
    ) -> list[HealthLogRow]:
        c = health_logs.c
        query = select(c.type, c.recorded_at, c.data, c.source, c.agent).where(
            c.user_id == user_id, c.type.in_(list(types))
        )
        if since is not None:
            query = query.where(c.recorded_at >= since)
        if agent is not None:
            query = query.where(c.agent == agent)
        for key, value in (data_equals or {}).items():
            query = query.where(c.data[key].astext == value)
        query = query.order_by(c.recorded_at.desc())
        if limit is not None:
            query = query.limit(limit)
        return [
            HealthLogRow(
                type=r.type,
                recorded_at=r.recorded_at,
                data=dict(r.data or {}),
                source=r.source,
                agent=r.agent,
            )
            for r in await self._conn.execute(query)
        ]

    async def add(self, user_id: UUID, row: HealthLogRow) -> datetime:
        when = row.recorded_at.astimezone(UTC)
        c = health_logs.c
        for _ in range(_MAX_SHIFTS):
            statement = (
                insert(health_logs)
                .values(
                    user_id=user_id,
                    agent=row.agent,
                    type=row.type,
                    source=row.source,
                    recorded_at=when,
                    data=dict(row.data),
                )
                .on_conflict_do_nothing(index_elements=[c.user_id, c.source, c.type, c.recorded_at])
                .returning(c.id)
            )
            if (await self._conn.execute(statement)).first() is not None:
                return when
            when += _ONE_US
        raise RuntimeError("no free timestamp for the health log row")

    async def upsert(self, user_id: UUID, row: HealthLogRow) -> bool:
        c = health_logs.c
        statement = insert(health_logs).values(
            user_id=user_id,
            agent=row.agent,
            type=row.type,
            source=row.source,
            recorded_at=row.recorded_at.astimezone(UTC),
            data=dict(row.data),
        )
        upsert = statement.on_conflict_do_update(
            index_elements=[c.user_id, c.source, c.type, c.recorded_at],
            set_={"data": statement.excluded.data},
            where=c.data.is_distinct_from(statement.excluded.data),
        ).returning(c.id)
        return (await self._conn.execute(upsert)).first() is not None
