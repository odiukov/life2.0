from __future__ import annotations

from collections.abc import Callable, Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.adapters.secrets import open_json, seal_json
from shared.ports.credentials import CredentialsUnreadable
from shared.ports.household_credentials import HouseholdConnection, NoHousehold
from shared.ports.secrets import SecretBox, SecretsUnreadable
from shared.schema.tables import household_credentials as hc
from shared.schema.tables import household_members as members

_CURRENT = text("SELECT public.current_household_id()")


class SqlHouseholdCredentials:
    def __init__(self, conn: AsyncConnection, box: SecretBox) -> None:
        self._conn = conn
        self._box = box

    async def _household(self) -> UUID | None:
        value = (await self._conn.execute(_CURRENT)).scalar_one_or_none()
        return value if isinstance(value, UUID) else None

    async def household_id(self) -> UUID | None:
        return await self._household()

    async def get(self, service: str) -> HouseholdConnection | None:
        household = await self._household()
        if household is None:
            return None
        row = (
            await self._conn.execute(
                select(
                    hc.c.payload_enc,
                    hc.c.version,
                    hc.c.updated_by,
                    hc.c.updated_at,
                    members.c.display_name,
                )
                .select_from(
                    hc.outerjoin(
                        members,
                        (members.c.user_id == hc.c.updated_by)
                        & (members.c.household_id == hc.c.household_id),
                    )
                )
                .where(hc.c.household_id == household, hc.c.service == service)
            )
        ).one_or_none()
        if row is None:
            return None
        try:
            payload = open_json(self._box, bytes(row.payload_enc))
        except SecretsUnreadable as exc:
            raise CredentialsUnreadable(service) from exc
        return HouseholdConnection(
            household, payload, row.version, row.updated_by, row.display_name, row.updated_at
        )

    async def put(
        self, service: str, payload: Mapping[str, Any], *, actor: UUID
    ) -> HouseholdConnection:
        household = await self._household()
        if household is None:
            raise NoHousehold
        sealed = seal_json(self._box, dict(payload))
        now = datetime.now(UTC)
        statement = insert(hc).values(
            household_id=household,
            service=service,
            payload_enc=sealed,
            version=text("nextval('household_credentials_version_seq')"),
            updated_by=actor,
            updated_at=now,
        )
        row = (
            await self._conn.execute(
                statement.on_conflict_do_update(
                    index_elements=[hc.c.household_id, hc.c.service],
                    set_={
                        "payload_enc": sealed,
                        "version": statement.excluded.version,
                        "updated_by": actor,
                        "updated_at": now,
                    },
                ).returning(hc.c.version)
            )
        ).one()
        name = (
            await self._conn.execute(
                select(members.c.display_name).where(members.c.user_id == actor)
            )
        ).scalar_one_or_none()
        return HouseholdConnection(household, dict(payload), row.version, actor, name, now)

    async def delete(self, service: str) -> bool:
        household = await self._household()
        if household is None:
            return False
        result = await self._conn.execute(
            delete(hc)
            .where(hc.c.household_id == household, hc.c.service == service)
            .returning(hc.c.service)
        )
        return result.first() is not None


def sql_household_credentials(
    box: SecretBox,
) -> Callable[[AsyncConnection], SqlHouseholdCredentials]:
    def factory(conn: AsyncConnection) -> SqlHouseholdCredentials:
        return SqlHouseholdCredentials(conn, box)

    return factory
