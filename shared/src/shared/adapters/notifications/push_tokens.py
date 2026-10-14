from __future__ import annotations

from datetime import datetime
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.schema.tables import push_tokens


class SqlPushTokens:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def upsert(self, user_id: UUID, token: str, platform: str, *, at: datetime) -> None:
        # This function moves a token previously registered by another user of the device.
        await self._conn.execute(
            text("SELECT public.push_token_claim(CAST(:t AS text), CAST(:p AS text))"),
            {"t": token, "p": platform},
        )

    async def delete(self, user_id: UUID, token: str) -> None:
        await self._conn.execute(
            delete(push_tokens).where(
                push_tokens.c.user_id == user_id, push_tokens.c.token == token
            )
        )

    async def for_user(self, user_id: UUID) -> list[str]:
        rows = await self._conn.execute(
            select(push_tokens.c.token)
            .where(push_tokens.c.user_id == user_id)
            .order_by(push_tokens.c.token)
        )
        return [r.token for r in rows]
