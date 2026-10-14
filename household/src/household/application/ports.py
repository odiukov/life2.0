from __future__ import annotations

from datetime import datetime, time
from typing import Protocol
from uuid import UUID

from household.domain.model import Household, InvitePreview


class HouseholdRepository(Protocol):
    """Membership operations. SQL derives the actor from the unit of work's tenant."""

    async def ensure(self, user_id: UUID, *, name: str, timezone: str) -> UUID: ...

    async def get(self, user_id: UUID) -> Household:
        """Raises NoHousehold."""
        ...

    async def update(
        self, user_id: UUID, *, name: str | None, timezone: str | None, digest_time: time | None
    ) -> None:
        """Raises NotOwner / NoHousehold."""
        ...

    async def create_invite(
        self, user_id: UUID, *, code_hash: bytes, expires_at: datetime
    ) -> None: ...

    async def preview(self, user_id: UUID, code_hash: bytes) -> InvitePreview:
        """Raises InviteInvalid / InviteOwnHousehold / InviteRateLimited."""
        ...

    async def join(self, user_id: UUID, code_hash: bytes) -> UUID:
        """Same errors as preview; returns the joined household id."""
        ...

    async def leave(self, user_id: UUID) -> UUID:
        """Raises SoleMember / NoHousehold; returns the leaver's fresh household id."""
        ...

    async def remove_member(self, user_id: UUID, member_id: UUID) -> None:
        """Raises NotOwner / CannotRemoveSelf / NotMember / NoHousehold."""
        ...
