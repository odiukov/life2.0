"""Bounded household MCP sessions, each entered and exited by its own owning task."""

from __future__ import annotations

import asyncio
import contextlib
from dataclasses import dataclass
from time import monotonic
from uuid import UUID

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools
from shared.observability.logging import get_logger
from shared.ports.household_credentials import HouseholdConnection

from home.application.ports import HomeUnavailable

MCP_PATH = "/mcp_server/sse"
SERVER = "home-assistant"
logger = get_logger(__name__)


@dataclass
class _Entry:
    version: int
    opened: float
    ready: asyncio.Future[list[BaseTool]]
    stop: asyncio.Event
    task: asyncio.Task[None]


class McpPool:
    def __init__(
        self, *, ttl_s: float = 600.0, connect_timeout_s: float = 10.0, max_households: int = 32
    ) -> None:
        if ttl_s <= 0 or connect_timeout_s <= 0 or max_households < 1:
            raise ValueError("invalid_pool_limits")
        self._ttl, self._timeout, self._max = ttl_s, connect_timeout_s, max_households
        self._entries: dict[UUID, _Entry] = {}
        self._lock = asyncio.Lock()

    async def _serve(
        self, conn: HouseholdConnection, ready: asyncio.Future[list[BaseTool]], stop: asyncio.Event
    ) -> None:
        try:
            client = MultiServerMCPClient(
                {
                    SERVER: {
                        "url": f"{conn.payload['base_url']}{MCP_PATH}",
                        "transport": "sse",
                        "headers": {"Authorization": f"Bearer {conn.payload['token']}"},
                    }
                }
            )
            async with client.session(SERVER) as session:
                loaded = await load_mcp_tools(session)
                if not ready.done():
                    ready.set_result(loaded)
                await stop.wait()
        except Exception as exc:
            logger.warning("home_mcp_unavailable", error_type=type(exc).__name__)
            if not ready.done():
                ready.set_exception(HomeUnavailable())
        finally:
            if not ready.done():
                ready.cancel()

    async def tools(self, conn: HouseholdConnection) -> list[BaseTool]:
        async with self._lock:
            house = conn.household_id
            entry = self._entries.get(house)
            if (
                entry is not None
                and entry.version == conn.version
                and monotonic() - entry.opened < self._ttl
                and not entry.task.done()
            ):
                return entry.ready.result()
            await self._close(house)
            if len(self._entries) >= self._max:
                await self._close(min(self._entries, key=lambda h: self._entries[h].opened))
            ready: asyncio.Future[list[BaseTool]] = asyncio.get_running_loop().create_future()
            stop = asyncio.Event()
            task = asyncio.create_task(self._serve(conn, ready, stop))
            self._entries[house] = _Entry(conn.version, monotonic(), ready, stop, task)
            try:
                return await asyncio.wait_for(asyncio.shield(ready), self._timeout)
            except BaseException as exc:
                task.cancel()
                await self._close(house)
                if isinstance(exc, asyncio.CancelledError):
                    raise
                raise HomeUnavailable from None

    async def _close(self, house: UUID) -> None:
        entry = self._entries.pop(house, None)
        if entry is not None:
            entry.stop.set()
            with contextlib.suppress(asyncio.CancelledError):
                await entry.task
            if entry.ready.done() and not entry.ready.cancelled():
                entry.ready.exception()

    async def aclose(self) -> None:
        async with self._lock:
            for house in list(self._entries):
                await self._close(house)
