from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from enum import StrEnum
from uuid import UUID


class Role(StrEnum):
    OWNER = "owner"
    MEMBER = "member"


@dataclass(frozen=True, slots=True)
class Member:
    user_id: UUID
    display_name: str
    role: Role
    joined_at: datetime


@dataclass(frozen=True, slots=True)
class Household:
    id: UUID
    name: str
    timezone: str
    digest_time: time
    members: tuple[Member, ...]

    def role_of(self, user_id: UUID) -> Role | None:
        return next((m.role for m in self.members if m.user_id == user_id), None)


@dataclass(frozen=True, slots=True)
class InvitePreview:
    household_name: str
    member_count: int
    items_to_move: int
