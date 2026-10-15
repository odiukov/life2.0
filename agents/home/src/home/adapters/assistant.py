from __future__ import annotations

import asyncio
from collections.abc import Mapping

import httpx
from mcp.shared.exceptions import McpError
from mcp.types import CONNECTION_CLOSED
from shared.ports.household_credentials import HouseholdConnection

from home.adapters.mcp_pool import McpPool
from home.application.ports import HomeUnavailable, InvalidToken, ToolRejected


class HttpHomeAssistant:
    def __init__(self, http: httpx.AsyncClient, pool: McpPool, *, timeout_s: float = 5.0) -> None:
        self._http = http
        self._pool = pool
        self._timeout = timeout_s

    async def ping(self, base_url: str, token: str) -> str | None:
        try:
            response = await self._http.get(
                f"{base_url}/api/",
                headers={"Authorization": f"Bearer {token}"},
                timeout=self._timeout,
            )
        except httpx.HTTPError:
            raise HomeUnavailable from None
        if response.status_code == 401:
            raise InvalidToken
        if response.status_code != 200:
            raise HomeUnavailable
        try:
            body = response.json()
            version = body.get("version") if isinstance(body, dict) else None
        except ValueError:
            return None
        return str(version) if version else None

    async def call_tool(
        self, conn: HouseholdConnection, tool: str, args: Mapping[str, object]
    ) -> None:
        try:
            async with asyncio.timeout(self._timeout):
                tools = {t.name: t for t in await self._pool.tools(conn)}
                if tool not in tools:
                    raise ToolRejected
                await tools[tool].ainvoke(dict(args))
        except HomeUnavailable:
            raise
        except (httpx.HTTPError, TimeoutError, ConnectionError, OSError):
            raise HomeUnavailable from None
        except McpError as exc:
            if exc.error.code in (httpx.codes.REQUEST_TIMEOUT, CONNECTION_CLOSED):
                raise HomeUnavailable from None
            raise ToolRejected from None
        except Exception as exc:  # MCP surfaces genuine tool failures as ToolException.
            raise ToolRejected(type(exc).__name__) from None
