"""Credentials shared by a household (Home Assistant). The tenant's household is implicit (RLS)."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from uuid import UUID


class NoHousehold(Exception):
    """The tenant belongs to no household."""


@dataclass(frozen=True, slots=True)
class HouseholdConnection:
    household_id: UUID
    payload: dict[str, Any]
    version: int
    updated_by: UUID | None
    updated_by_name: str | None
    updated_at: datetime


class HouseholdCredentialStore(Protocol):
    async def get(self, service: str) -> HouseholdConnection | None:
        """None without a household or a connection; raises CredentialsUnreadable."""
        ...

    async def put(
        self, service: str, payload: Mapping[str, Any], *, actor: UUID
    ) -> HouseholdConnection:
        """Replace the connection of the tenant's household and bump its version; raises NoHousehold."""
        ...

    async def delete(self, service: str) -> bool: ...

    async def household_id(self) -> UUID | None:
        """The tenant's household, or None."""
        ...
