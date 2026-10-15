import asyncio
import socket
from datetime import UTC, datetime
from uuid import uuid4

import pytest
import uvicorn
from home.adapters.mcp_pool import MCP_PATH, McpPool
from home.application.ports import HomeUnavailable
from mcp.server.fastmcp import FastMCP
from shared.ports.household_credentials import HouseholdConnection

pytestmark = pytest.mark.integration


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
async def ha_server():
    mcp = FastMCP("ha", sse_path=MCP_PATH, message_path="/mcp_server/messages/")

    @mcp.tool()
    def GetLiveContext() -> str:
        return "Lamp: on"

    port = _free_port()
    server = uvicorn.Server(
        uvicorn.Config(mcp.sse_app(), host="127.0.0.1", port=port, log_level="warning")
    )
    task = asyncio.create_task(server.serve())
    while not server.started:  # noqa: ASYNC110 -- uvicorn exposes a flag, not an event.
        await asyncio.sleep(0.05)
    try:
        yield f"http://127.0.0.1:{port}"
    finally:
        server.should_exit = True
        await task


async def test_pool_lists_reuses_and_reconnects(ha_server: str) -> None:
    house = uuid4()
    pool = McpPool(ttl_s=60)
    v1 = HouseholdConnection(
        house, {"base_url": ha_server, "token": "t"}, 1, None, None, datetime.now(UTC)
    )
    first = await pool.tools(v1)
    assert [t.name for t in first] == ["GetLiveContext"]
    assert (await first[0].ainvoke({}))[0]["text"] == "Lamp: on"
    assert await pool.tools(v1) is first
    v2 = HouseholdConnection(
        house, {"base_url": ha_server, "token": "t2"}, 2, None, None, datetime.now(UTC)
    )
    assert await pool.tools(v2) is not first
    await pool.aclose()


async def test_unreachable_server_is_home_unavailable() -> None:
    pool = McpPool(connect_timeout_s=1)
    dead = HouseholdConnection(
        uuid4(),
        {"base_url": f"http://127.0.0.1:{_free_port()}", "token": "t"},
        1,
        None,
        None,
        datetime.now(UTC),
    )
    with pytest.raises(HomeUnavailable):
        await pool.tools(dead)


async def test_pool_sessions_survive_the_request_task_and_close_elsewhere(ha_server: str) -> None:
    pool = McpPool(ttl_s=60)
    conn = HouseholdConnection(
        uuid4(), {"base_url": ha_server, "token": "t"}, 1, None, None, datetime.now(UTC)
    )

    async def request():
        return await pool.tools(conn)

    tools = await asyncio.create_task(request())
    assert await tools[0].ainvoke({})
    await asyncio.create_task(pool.aclose())
    assert not pool._entries
