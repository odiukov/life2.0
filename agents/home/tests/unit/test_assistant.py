from datetime import UTC, datetime
from uuid import uuid4

import httpx
import pytest
from home.adapters.assistant import HttpHomeAssistant
from home.application.ports import HomeUnavailable, InvalidToken, ToolRejected
from langchain_core.tools import tool
from shared.ports.household_credentials import HouseholdConnection


class Pool:
    async def tools(self, conn):
        return []


@pytest.mark.parametrize(("status", "error"), [(401, InvalidToken), (503, HomeUnavailable)])
async def test_ping_maps_http_failures(status, error) -> None:
    async with httpx.AsyncClient(
        transport=httpx.MockTransport(lambda request: httpx.Response(status))
    ) as client:
        with pytest.raises(error):
            await HttpHomeAssistant(client, Pool()).ping("http://ha", "token")


@pytest.mark.parametrize(
    ("body", "expected"),
    [({"version": "2026.10"}, "2026.10"), ({"message": "API running."}, None), ([], None)],
)
async def test_ping_extracts_optional_version(body, expected) -> None:
    def handler(request):
        assert request.url.path == "/api/"
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(200, json=body)

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        assert await HttpHomeAssistant(client, Pool()).ping("http://ha", "token") == expected


async def test_unknown_confirmed_tool_is_rejected() -> None:
    conn = HouseholdConnection(uuid4(), {}, 1, None, None, datetime.now(UTC))
    async with httpx.AsyncClient() as client:
        with pytest.raises(ToolRejected):
            await HttpHomeAssistant(client, Pool()).call_tool(conn, "missing", {})


async def test_tool_failure_is_rejected() -> None:
    @tool
    async def HassTurnOff() -> str:
        """Turn off the lamp."""
        raise ValueError("rejected")

    class RejectingPool:
        async def tools(self, conn):
            return [HassTurnOff]

    conn = HouseholdConnection(uuid4(), {}, 1, None, None, datetime.now(UTC))
    async with httpx.AsyncClient() as client:
        with pytest.raises(ToolRejected):
            await HttpHomeAssistant(client, RejectingPool()).call_tool(conn, "HassTurnOff", {})


async def test_tool_transport_failure_is_unavailable() -> None:
    @tool
    async def HassTurnOff() -> str:
        """Turn off the lamp."""
        raise httpx.ConnectError("private connection details")

    class OfflinePool:
        async def tools(self, conn):
            return [HassTurnOff]

    conn = HouseholdConnection(uuid4(), {}, 1, None, None, datetime.now(UTC))
    async with httpx.AsyncClient() as client:
        with pytest.raises(HomeUnavailable):
            await HttpHomeAssistant(client, OfflinePool()).call_tool(conn, "HassTurnOff", {})


async def test_hanging_confirmed_tool_has_a_response_deadline() -> None:
    import asyncio

    cancelled = asyncio.Event()

    @tool
    async def HassTurnOff() -> str:
        """Turn off the lamp."""
        try:
            await asyncio.Event().wait()
        finally:
            cancelled.set()
        return "done"

    class HangingPool:
        async def tools(self, conn):
            return [HassTurnOff]

    conn = HouseholdConnection(uuid4(), {}, 1, None, None, datetime.now(UTC))
    async with httpx.AsyncClient() as client:
        async with asyncio.timeout(0.5):
            with pytest.raises(HomeUnavailable):
                await HttpHomeAssistant(client, HangingPool(), timeout_s=0.02).call_tool(
                    conn, "HassTurnOff", {}
                )
    assert cancelled.is_set()


@pytest.mark.parametrize(
    ("code", "expected"),
    [(408, HomeUnavailable), (-32000, HomeUnavailable), (-32602, ToolRejected)],
)
async def test_mcp_sdk_errors_distinguish_unavailability_from_rejection(code, expected) -> None:
    from mcp.shared.exceptions import McpError
    from mcp.types import ErrorData

    @tool
    async def HassTurnOff() -> str:
        """Turn off the lamp."""
        raise McpError(ErrorData(code=code, message="private server details"))

    class ErrorPool:
        async def tools(self, conn):
            return [HassTurnOff]

    conn = HouseholdConnection(uuid4(), {}, 1, None, None, datetime.now(UTC))
    async with httpx.AsyncClient() as client:
        with pytest.raises(expected):
            await HttpHomeAssistant(client, ErrorPool()).call_tool(conn, "HassTurnOff", {})
