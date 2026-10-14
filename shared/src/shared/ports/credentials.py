from __future__ import annotations

from collections.abc import Mapping
from typing import Any, Protocol
from uuid import UUID


class CredentialsUnreadable(Exception):
    """Stored credentials exist but cannot be opened (wrong SECRETS__KEY or a damaged row)."""


class CredentialStore(Protocol):
    async def get(self, user_id: UUID, service: str) -> dict[str, Any] | None:
        """None when the integration is not connected; raises CredentialsUnreadable."""
        ...

    async def put(self, user_id: UUID, service: str, payload: Mapping[str, Any]) -> None:
        """Replace the credentials of this service."""
        ...

    async def merge(self, user_id: UUID, service: str, changes: Mapping[str, Any]) -> None:
        """Merge keys (e.g. a refreshed token) into existing credentials; no-op when absent."""
        ...

    async def delete(self, user_id: UUID, service: str) -> None: ...
