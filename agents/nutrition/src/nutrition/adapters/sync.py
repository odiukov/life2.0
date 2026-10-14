"""Best-effort trigger of the sync service's nutrition refresh (Yazio)."""

from __future__ import annotations

import asyncio

import httpx
from shared.observability.logging import get_logger

logger = get_logger(__name__)


class HttpNutritionSync:
    def __init__(
        self,
        base_url: str | None,
        *,
        timeout_s: float = 5.0,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._url = f"{base_url.rstrip('/')}/sync/nutrition" if base_url else None
        self._timeout_s = timeout_s
        self._client = client

    async def refresh(self) -> None:
        if self._url is None:
            return
        try:
            # Bound the entire refresh, including client setup and cleanup. httpx's
            # phase timeouts alone do not limit the complete request duration.
            async with asyncio.timeout(self._timeout_s) as deadline:
                if self._client is not None:
                    response = await self._client.post(self._url, timeout=self._timeout_s)
                    response.raise_for_status()
                else:
                    client = httpx.AsyncClient(timeout=self._timeout_s)
                    request_cancelled = False
                    try:
                        response = await client.post(self._url)
                        response.raise_for_status()
                    except asyncio.CancelledError:
                        request_cancelled = True
                        raise
                    finally:
                        # Request cancellation already spent the outer timeout's
                        # cancellation. Closing needs its own timer at the same
                        # deadline, even when that deadline has passed. Cooperative
                        # cleanup may be interrupted; no task is left running.
                        cleanup_deadline = asyncio.timeout_at(deadline.when())
                        try:
                            async with cleanup_deadline:
                                await client.aclose()
                        except Exception as exc:
                            # Cleanup cannot replace a pending cancellation. Without
                            # cancellation, suppress only our timer's expiration.
                            if not request_cancelled and not (
                                isinstance(exc, TimeoutError) and cleanup_deadline.expired()
                            ):
                                raise
        except (httpx.HTTPError, TimeoutError) as exc:
            # Stale data is acceptable; log metadata only, never URL or error text.
            logger.warning("nutrition_sync_failed", error_type=type(exc).__name__)
