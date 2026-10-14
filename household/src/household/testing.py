"""In-memory HouseholdRepository with the same contract as the SQL functions.

Operations do not yield, so membership and rate checks are atomic within an event loop.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime, time, timedelta
from uuid import UUID, uuid4

from shared.ports.clock import Clock
from shared.testing.fakes import InMemoryUnitOfWorkFactory

from household.application.ports import HouseholdRepository
from household.domain.errors import (
    CannotRemoveSelf,
    InviteInvalid,
    InviteOwnHousehold,
    InviteRateLimited,
    NoHousehold,
    NotMember,
    NotOwner,
    SoleMember,
)
from household.domain.model import Household, InvitePreview, Member, Role

RATE_LIMIT = 5
RATE_WINDOW = timedelta(hours=1)
ATTEMPT_RETENTION = timedelta(hours=24)


@dataclass
class _Row:
    name: str
    timezone: str
    digest_time: time = time(18, 0)
    members: list[Member] = field(default_factory=list)


@dataclass
class _Invite:
    household_id: UUID
    expires_at: datetime
    redeemed: bool = False


class InMemoryHouseholds:
    def __init__(
        self,
        clock: Clock,
        *,
        item_count: Callable[[UUID], int] = lambda household_id: 0,
        on_move: Callable[[UUID, UUID], None] = lambda old, new: None,
    ) -> None:
        self._clock = clock
        self._item_count = item_count
        self._on_move = on_move
        self.households: dict[UUID, _Row] = {}
        self.invites: dict[bytes, _Invite] = {}
        self.failures: dict[UUID, list[datetime]] = {}

    def _mine(self, user_id: UUID) -> UUID | None:
        return next(
            (
                hid
                for hid, row in self.households.items()
                if any(m.user_id == user_id for m in row.members)
            ),
            None,
        )

    def _member(self, household_id: UUID, user_id: UUID) -> Member:
        return next(m for m in self.households[household_id].members if m.user_id == user_id)

    def _new_for(self, user_id: UUID, name: str, timezone: str) -> UUID:
        hid = uuid4()
        self.households[hid] = _Row(
            name, timezone, members=[Member(user_id, name, Role.OWNER, self._clock.now())]
        )
        return hid

    def _drop(self, household_id: UUID, user_id: UUID) -> Member:
        row = self.households[household_id]
        member = self._member(household_id, user_id)
        row.members.remove(member)
        if member.role is Role.OWNER and row.members:
            first = min(row.members, key=lambda m: (m.joined_at, str(m.user_id)))
            row.members[row.members.index(first)] = replace(first, role=Role.OWNER)
        return member

    def _check(self, user_id: UUID, code_hash: bytes) -> tuple[_Invite, UUID | None]:
        now = self._clock.now()
        for actor, attempts in list(self.failures.items()):
            retained = [t for t in attempts if t >= now - ATTEMPT_RETENTION]
            if retained:
                self.failures[actor] = retained
            else:
                del self.failures[actor]
        recent = [t for t in self.failures.get(user_id, []) if t > now - RATE_WINDOW]
        if len(recent) >= RATE_LIMIT:
            raise InviteRateLimited
        invite = self.invites.get(code_hash)
        if invite is None or invite.redeemed or invite.expires_at <= now:
            self.failures.setdefault(user_id, []).append(now)
            raise InviteInvalid
        mine = self._mine(user_id)
        if mine == invite.household_id:
            raise InviteOwnHousehold
        return invite, mine

    async def ensure(self, user_id: UUID, *, name: str, timezone: str) -> UUID:
        return self._mine(user_id) or self._new_for(user_id, name, timezone)

    async def get(self, user_id: UUID) -> Household:
        hid = self._mine(user_id)
        if hid is None:
            raise NoHousehold
        row = self.households[hid]
        members = tuple(sorted(row.members, key=lambda m: (m.joined_at, str(m.user_id))))
        return Household(hid, row.name, row.timezone, row.digest_time, members)

    async def update(
        self, user_id: UUID, *, name: str | None, timezone: str | None, digest_time: time | None
    ) -> None:
        hid = self._mine(user_id)
        if hid is None:
            raise NoHousehold
        if self._member(hid, user_id).role is not Role.OWNER:
            raise NotOwner
        row = self.households[hid]
        row.name = name if name is not None else row.name
        row.timezone = timezone if timezone is not None else row.timezone
        row.digest_time = digest_time if digest_time is not None else row.digest_time

    async def create_invite(self, user_id: UUID, *, code_hash: bytes, expires_at: datetime) -> None:
        hid = self._mine(user_id)
        if hid is None:
            raise NoHousehold
        self.invites[code_hash] = _Invite(hid, expires_at)

    async def preview(self, user_id: UUID, code_hash: bytes) -> InvitePreview:
        invite, mine = self._check(user_id, code_hash)
        target = self.households[invite.household_id]
        sole = mine is not None and len(self.households[mine].members) == 1
        return InvitePreview(
            target.name, len(target.members), self._item_count(mine) if sole and mine else 0
        )

    async def join(self, user_id: UUID, code_hash: bytes) -> UUID:
        invite, mine = self._check(user_id, code_hash)
        display = f"user:{str(user_id)[:8]}"
        if mine is not None:
            sole = len(self.households[mine].members) == 1
            display = self._drop(mine, user_id).display_name
            if sole:
                self._on_move(mine, invite.household_id)
                del self.households[mine]
                self.invites = {
                    digest: existing
                    for digest, existing in self.invites.items()
                    if existing.household_id != mine
                }
        self.households[invite.household_id].members.append(
            Member(user_id, display, Role.MEMBER, self._clock.now())
        )
        invite.redeemed = True
        return invite.household_id

    async def leave(self, user_id: UUID) -> UUID:
        hid = self._mine(user_id)
        if hid is None:
            raise NoHousehold
        if len(self.households[hid].members) == 1:
            raise SoleMember
        timezone = self.households[hid].timezone
        member = self._drop(hid, user_id)
        return self._new_for(user_id, member.display_name, timezone)

    async def remove_member(self, user_id: UUID, member_id: UUID) -> None:
        hid = self._mine(user_id)
        if hid is None:
            raise NoHousehold
        if self._member(hid, user_id).role is not Role.OWNER:
            raise NotOwner
        if member_id == user_id:
            raise CannotRemoveSelf
        if not any(m.user_id == member_id for m in self.households[hid].members):
            raise NotMember
        timezone = self.households[hid].timezone
        member = self._drop(hid, member_id)
        self._new_for(member_id, member.display_name, timezone)


def in_memory_uow(households: InMemoryHouseholds) -> InMemoryUnitOfWorkFactory:
    return InMemoryUnitOfWorkFactory({HouseholdRepository: households})
