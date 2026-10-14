from __future__ import annotations

from datetime import datetime, timedelta
from uuid import UUID

from shared.adapters.db.credentials import sql_credential_store
from shared.adapters.db.health_logs import SqlHealthLogs
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.db.users import SqlUserSettings
from shared.ports.credentials import CredentialStore
from shared.ports.health_logs import HealthLogRepository
from shared.ports.secrets import SecretBox
from shared.ports.users import UserSettingsRepository
from shared.schema.tables import integration_sync_state as state
from sqlalchemy import or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from sync.application.ports import Service, SyncStateRepository, SyncStatus


class SqlSyncState:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def get(self, user_id: UUID, service: Service) -> SyncStatus | None:
        row = (
            await self._conn.execute(
                select(state.c.last_attempt_at, state.c.last_success_at, state.c.last_error).where(
                    state.c.user_id == user_id, state.c.service == service
                )
            )
        ).one_or_none()
        return SyncStatus(row.last_attempt_at, row.last_success_at, row.last_error) if row else None

    async def claim(
        self, user_id: UUID, service: Service, *, now: datetime, cooldown: timedelta
    ) -> bool:
        statement = insert(state).values(user_id=user_id, service=service, last_attempt_at=now)
        claimed = statement.on_conflict_do_update(
            index_elements=[state.c.user_id, state.c.service],
            set_={"last_attempt_at": now},
            where=or_(state.c.last_attempt_at.is_(None), state.c.last_attempt_at <= now - cooldown),
        ).returning(state.c.user_id)
        return (await self._conn.execute(claimed)).first() is not None

    async def finish(
        self, user_id: UUID, service: Service, *, now: datetime, error: str | None, success: bool
    ) -> None:
        values: dict[str, object] = {"last_attempt_at": now, "last_error": error}
        if success:
            values["last_success_at"] = now
        statement = insert(state).values(user_id=user_id, service=service, **values)
        await self._conn.execute(
            statement.on_conflict_do_update(
                index_elements=[state.c.user_id, state.c.service], set_=values
            )
        )


def sync_uow(engine: AsyncEngine, box: SecretBox) -> SqlUnitOfWorkFactory:
    return SqlUnitOfWorkFactory(
        engine,
        {
            CredentialStore: sql_credential_store(box),
            HealthLogRepository: SqlHealthLogs,
            UserSettingsRepository: SqlUserSettings,
            SyncStateRepository: SqlSyncState,
        },
    )
