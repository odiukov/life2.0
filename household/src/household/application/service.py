from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime, time, timedelta
from typing import TypeVar
from uuid import UUID
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from shared.ports.clock import Clock
from shared.ports.uow import UnitOfWorkFactory

from household.application.ports import HouseholdRepository
from household.domain.errors import HouseholdError, InvalidSettings, InviteInvalid
from household.domain.invite import InviteCode
from household.domain.model import Household, InvitePreview

T = TypeVar("T")
INVITE_TTL = timedelta(hours=48)
NAME_MAX = 60
# Never a valid code digest: lets malformed input count as a failed attempt in the database.
_MALFORMED = b"\x00" * 32


@dataclass(frozen=True, slots=True)
class HouseholdChanges:
    name: str | None = None
    timezone: str | None = None
    digest_time: time | None = None


@dataclass(frozen=True, slots=True)
class CreatedInvite:
    code: InviteCode
    expires_at: datetime


def _valid_zone(name: str) -> str:
    try:
        ZoneInfo(name)
    except (ZoneInfoNotFoundError, ValueError) as exc:
        raise InvalidSettings from exc
    return name


def _digest(raw: str) -> bytes:
    try:
        return InviteCode.parse(raw).digest()
    except InviteInvalid:
        return _MALFORMED


class HouseholdService:
    def __init__(
        self,
        uow: UnitOfWorkFactory,
        clock: Clock,
        *,
        new_code: Callable[[], InviteCode] = InviteCode.generate,
    ) -> None:
        self._uow = uow
        self._clock = clock
        self._new_code = new_code

    async def ensure(self, user_id: UUID) -> UUID:
        async with self._uow.for_user(user_id) as uow:
            return await uow.repo(HouseholdRepository).ensure(
                user_id, name=f"user:{str(user_id)[:8]}", timezone="UTC"
            )

    async def get(self, user_id: UUID) -> Household:
        async with self._uow.for_user(user_id) as uow:
            return await uow.repo(HouseholdRepository).get(user_id)

    async def update(self, user_id: UUID, changes: HouseholdChanges) -> None:
        name = changes.name.strip() if changes.name is not None else None
        if name is not None and not 1 <= len(name) <= NAME_MAX:
            raise InvalidSettings
        timezone = _valid_zone(changes.timezone) if changes.timezone is not None else None
        digest_time = changes.digest_time
        if digest_time is not None and (
            digest_time.tzinfo is not None or digest_time.second or digest_time.microsecond
        ):
            raise InvalidSettings
        async with self._uow.for_user(user_id) as uow:
            await uow.repo(HouseholdRepository).update(
                user_id, name=name, timezone=timezone, digest_time=changes.digest_time
            )

    async def create_invite(self, user_id: UUID) -> CreatedInvite:
        code = self._new_code()
        expires_at = self._clock.now() + INVITE_TTL
        async with self._uow.for_user(user_id) as uow:
            await uow.repo(HouseholdRepository).create_invite(
                user_id, code_hash=code.digest(), expires_at=expires_at
            )
        return CreatedInvite(code, expires_at)

    async def preview(self, user_id: UUID, raw_code: str) -> InvitePreview:
        return await self._committed(user_id, lambda repo: repo.preview(user_id, _digest(raw_code)))

    async def join(self, user_id: UUID, raw_code: str) -> UUID:
        return await self._committed(user_id, lambda repo: repo.join(user_id, _digest(raw_code)))

    async def _committed(
        self, user_id: UUID, op: Callable[[HouseholdRepository], Awaitable[T]]
    ) -> T:
        """Commit even when the repository reports a domain error: failed attempts must stick."""
        error: HouseholdError | None = None
        result: T | None = None
        async with self._uow.for_user(user_id) as uow:
            try:
                result = await op(uow.repo(HouseholdRepository))
            except HouseholdError as exc:
                error = exc
        if error is not None:
            raise error
        assert result is not None
        return result

    async def leave(self, user_id: UUID) -> UUID:
        async with self._uow.for_user(user_id) as uow:
            return await uow.repo(HouseholdRepository).leave(user_id)

    async def remove_member(self, user_id: UUID, member_id: UUID) -> None:
        async with self._uow.for_user(user_id) as uow:
            await uow.repo(HouseholdRepository).remove_member(user_id, member_id)
