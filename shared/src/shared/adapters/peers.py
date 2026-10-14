"""PeerClient over legacy A2A helpers (parallel depth-one, best-effort calls)."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import date
from uuid import UUID

from shared import peer as legacy_peer
from shared.observability.logging import get_logger

LEGACY_UNAVAILABLE = "(данные недоступны)"
PEER_TIMEOUT_S = 20.0
logger = get_logger(__name__)


class A2APeerClient:
    def __init__(self, registry: Mapping[str, str] | None = None) -> None:
        if registry is None:
            registry = {
                name: info["url"] for name, info in legacy_peer.default_peer_registry().items()
            }
        self._registry = dict(registry)

    async def fetch_artifacts(
        self, *, user_id: UUID, wanted: Mapping[str, str], for_date: date | None = None
    ) -> dict[str, str]:
        if not wanted:
            return {}
        registry = {name: {"url": url} for name, url in self._registry.items()}
        try:
            # HTTP phase timeouts alone do not bound an active response stream.
            async with asyncio.timeout(PEER_TIMEOUT_S):
                texts = await legacy_peer.fetch_peer_artifacts(
                    registry,
                    dict(wanted),
                    needed=set(wanted),
                    user_id=str(user_id),
                    for_date=for_date.isoformat() if for_date else None,
                )
        except Exception as exc:
            logger.warning("peer_fetch_failed", error_type=type(exc).__name__)
            return {}
        return {
            name: text
            for name, text in texts.items()
            if text and text.strip() and text != LEGACY_UNAVAILABLE
        }
