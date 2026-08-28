"""Contract tests for orchestrator.app.mcp_tools.get_user_mcp_tools."""
from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

USER = UUID("dddddddd-dddd-dddd-dddd-dddddddddddd")


@pytest.mark.asyncio
async def test_empty_when_nothing_connected(monkeypatch):
    from orchestrator.app import mcp_tools, vault

    mcp_tools._USER_MCP_CACHE.clear()
    monkeypatch.setattr(vault, "get", AsyncMock(return_value=None))

    tools = await mcp_tools.get_user_mcp_tools(USER)
    assert tools == []


@pytest.mark.asyncio
async def test_cached_on_second_call(monkeypatch):
    from orchestrator.app import mcp_tools

    mcp_tools._USER_MCP_CACHE.clear()
    calls = {"n": 0}

    async def fake_build(user_id):
        calls["n"] += 1
        return []  # empty but not-None result

    monkeypatch.setattr(mcp_tools, "_build_tools_for_user", fake_build)

    out1 = await mcp_tools.get_user_mcp_tools(USER)
    out2 = await mcp_tools.get_user_mcp_tools(USER)
    assert out1 == out2 == []
    assert calls["n"] == 1  # second call served from cache


@pytest.mark.asyncio
async def test_invalidate_forces_rebuild(monkeypatch):
    from orchestrator.app import mcp_tools

    mcp_tools._USER_MCP_CACHE.clear()
    calls = {"n": 0}

    async def fake_build(user_id):
        calls["n"] += 1
        return []

    monkeypatch.setattr(mcp_tools, "_build_tools_for_user", fake_build)

    await mcp_tools.get_user_mcp_tools(USER)
    mcp_tools.invalidate_user_mcp_cache(USER)
    await mcp_tools.get_user_mcp_tools(USER)
    assert calls["n"] == 2


@pytest.mark.asyncio
async def test_cache_evicts_when_full(monkeypatch):
    from orchestrator.app import mcp_tools

    mcp_tools._USER_MCP_CACHE.clear()
    monkeypatch.setattr(mcp_tools, "_USER_MCP_MAX_ENTRIES", 3)

    async def fake_build(user_id):
        return []

    monkeypatch.setattr(mcp_tools, "_build_tools_for_user", fake_build)

    for i in range(5):
        await mcp_tools.get_user_mcp_tools(UUID(int=i))

    # After inserting 5 entries with max=3, only the last 3 remain
    assert len(mcp_tools._USER_MCP_CACHE) == 3


@pytest.mark.asyncio
async def test_user_mcp_tools_keep_session_open_until_invalidation(monkeypatch):
    from orchestrator.app import mcp_tools, vault

    mcp_tools._USER_MCP_CACHE.clear()
    await mcp_tools.close_mcp_sessions()
    monkeypatch.setattr(
        vault, "get", AsyncMock(return_value={"base_url": "http://ha:8123", "token": "t"})
    )

    class FakeTool:
        name = "HassTurnOn"

    class FakeSession:
        closed = False

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            FakeSession.closed = True
            return False

    class FakeClient:
        def __init__(self, servers):
            self.servers = servers

        def session(self, server_name):
            return FakeSession()

    async def fake_load_tools(_session, server_name=None):
        return [FakeTool()]

    monkeypatch.setattr(mcp_tools, "MultiServerMCPClient", FakeClient)
    monkeypatch.setattr(mcp_tools, "_adapter_load_tools", fake_load_tools)

    tools = await mcp_tools.get_user_mcp_tools(USER)

    assert [t.name for t in tools] == ["HassTurnOn"]
    assert FakeSession.closed is False

    mcp_tools.invalidate_user_mcp_cache(USER)
    await asyncio.sleep(0)
    assert FakeSession.closed is True
