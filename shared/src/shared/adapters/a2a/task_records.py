"""TaskRecords on SQLAlchemy; same upsert as legacy shared.db.insert_task_record."""

from __future__ import annotations

from collections.abc import Mapping
from uuid import UUID

from sqlalchemy import func
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncEngine

from shared.schema.tables import tasks


class SqlTaskRecords:
    def __init__(self, engine: AsyncEngine) -> None:
        self._engine = engine

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
        statement = insert(tasks).values(
            task_id=UUID(task_id),
            context_id=UUID(context_id) if context_id else None,
            agent=agent,
            skill_id=skill_id,
            input=dict(input_),
            output=output,
            state=state,
        )
        statement = statement.on_conflict_do_update(
            index_elements=[tasks.c.task_id],
            set_={
                "output": statement.excluded.output,
                "state": statement.excluded.state,
                "updated_at": func.now(),
            },
        )
        async with self._engine.begin() as conn:
            await conn.execute(statement)
