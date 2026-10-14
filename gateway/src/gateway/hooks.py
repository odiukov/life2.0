from __future__ import annotations

import asyncio
from typing import Protocol
from uuid import UUID

from shared.observability.logging import get_logger

logger = get_logger(__name__)


class _Ensures(Protocol):
    async def ensure(self, user_id: UUID) -> UUID: ...


class HouseholdEnsurer:
    """Best-effort post-auth bootstrap; cache only successful household ensures."""

    def __init__(self, service: _Ensures) -> None:
        self._service = service
        self._seen: set[UUID] = set()
        self._locks: dict[UUID, asyncio.Lock] = {}

    async def __call__(self, user_id: UUID) -> None:
        if user_id in self._seen:
            return
        # Concurrent first requests must both wait for the same successful bootstrap.
        async with self._locks.setdefault(user_id, asyncio.Lock()):
            if user_id in self._seen:
                return
            try:
                await self._service.ensure(user_id)
            except Exception as exc:
                logger.warning("household_ensure_failed", error_type=type(exc).__name__)
                return
            self._seen.add(user_id)
