"""HouseholdRepository over the SECURITY DEFINER functions of c0002_household."""

from __future__ import annotations

from datetime import datetime, time
from uuid import UUID

from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.schema.tables import household_invites, household_members, households
from sqlalchemy import insert, select, text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from household.application.ports import HouseholdRepository
from household.domain.errors import (
    CannotRemoveSelf,
    HouseholdError,
    InviteInvalid,
    InviteOwnHousehold,
    InviteRateLimited,
    NoHousehold,
    NotMember,
    NotOwner,
    SoleMember,
)
from household.domain.model import Household, InvitePreview, Member, Role

_STATUS: dict[str, type[HouseholdError]] = {
    "invalid": InviteInvalid,
    "own": InviteOwnHousehold,
    "rate_limited": InviteRateLimited,
    "not_owner": NotOwner,
    "sole_member": SoleMember,
    "self": CannotRemoveSelf,
    "not_member": NotMember,
    "no_household": NoHousehold,
}


def _raise_for(status: str) -> None:
    if status != "ok":
        raise _STATUS.get(status, HouseholdError)()


class SqlHouseholdRepository:
    """The `user_id` arguments are informational: the tenant of the unit of work is the actor."""

    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def ensure(self, user_id: UUID, *, name: str, timezone: str) -> UUID:
        result = await self._conn.execute(
            text("SELECT household_ensure(:name, :tz)"), {"name": name, "tz": timezone}
        )
        return UUID(str(result.scalar_one()))

    async def get(self, user_id: UUID) -> Household:
        row = (
            await self._conn.execute(
                select(
                    households.c.id,
                    households.c.name,
                    households.c.timezone,
                    households.c.digest_time,
                )
            )
        ).one_or_none()
        if row is None:
            raise NoHousehold
        members = (
            await self._conn.execute(
                select(
                    household_members.c.user_id,
                    household_members.c.display_name,
                    household_members.c.role,
                    household_members.c.joined_at,
                ).order_by(household_members.c.joined_at, household_members.c.user_id)
            )
        ).all()
        return Household(
            id=row.id,
            name=row.name,
            timezone=row.timezone,
            digest_time=row.digest_time,
            members=tuple(
                Member(m.user_id, m.display_name, Role(m.role), m.joined_at) for m in members
            ),
        )

    async def update(
        self, user_id: UUID, *, name: str | None, timezone: str | None, digest_time: time | None
    ) -> None:
        status = (
            await self._conn.execute(
                text("SELECT household_update(:name, :tz, :dt)"),
                {"name": name, "tz": timezone, "dt": digest_time},
            )
        ).scalar_one()
        _raise_for(str(status))

    async def create_invite(self, user_id: UUID, *, code_hash: bytes, expires_at: datetime) -> None:
        await self._conn.execute(
            insert(household_invites).values(
                code_hash=code_hash,
                created_by=text("pg_catalog.current_setting('app.user_id')::uuid"),
                expires_at=expires_at,
            )
        )

    async def preview(self, user_id: UUID, code_hash: bytes) -> InvitePreview:
        row = (
            await self._conn.execute(
                text("SELECT * FROM household_invite_preview(:h)"), {"h": code_hash}
            )
        ).one()
        _raise_for(row.status)
        return InvitePreview(row.household_name, row.member_count, row.items_to_move)

    async def join(self, user_id: UUID, code_hash: bytes) -> UUID:
        row = (
            await self._conn.execute(text("SELECT * FROM household_join(:h)"), {"h": code_hash})
        ).one()
        _raise_for(row.status)
        return UUID(str(row.household_id))

    async def leave(self, user_id: UUID) -> UUID:
        row = (await self._conn.execute(text("SELECT * FROM household_leave()"))).one()
        _raise_for(row.status)
        return UUID(str(row.household_id))

    async def remove_member(self, user_id: UUID, member_id: UUID) -> None:
        status = (
            await self._conn.execute(text("SELECT household_remove_member(:u)"), {"u": member_id})
        ).scalar_one()
        _raise_for(str(status))


def household_uow(engine: AsyncEngine) -> SqlUnitOfWorkFactory:
    return SqlUnitOfWorkFactory(engine, {HouseholdRepository: SqlHouseholdRepository})
