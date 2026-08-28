"""Tests for per-server failure isolation in load_mcp_tools.

The loader used to wrap the whole multi-server loop in one try/except — any
single server failing poisoned the entire discovery pass (all-or-nothing).
Now a failure in server A must not prevent server B's tools from loading.
"""
from contextlib import asynccontextmanager

import pytest


@asynccontextmanager
async def _raising_session(*_args, **_kwargs):
    raise RuntimeError("server A is down")
    yield  # pragma: no cover — unreachable, keeps decorator happy


@asynccontextmanager
async def _ok_session(*_args, **_kwargs):
    yield object()  # opaque session handle; _adapter_load_tools is patched too


class _FakeTool:
    def __init__(self, name: str):
        self.name = name


def _two_servers() -> dict[str, dict]:
    """Two configured servers — isolation is only observable with more than one."""
    return {
        "server-a": {"url": "http://a.example/mcp", "transport": "streamable_http"},
        "home-assistant": {"url": "http://ha.example/mcp_server/sse", "transport": "sse"},
    }


@pytest.mark.asyncio
async def test_one_server_failure_does_not_block_others(monkeypatch):
    """If server A raises while opening a session, server B's tools still load."""
    from orchestrator.app import mcp_tools
    mcp_tools._MCP_TOOLS.clear()
    monkeypatch.setattr(mcp_tools, "_servers_from_env", _two_servers)

    class FakeClient:
        def __init__(self, servers):
            self.servers = servers

        def session(self, name):
            if name == "server-a":
                return _raising_session()
            return _ok_session()

    async def fake_load_tools(_session, server_name):
        assert server_name == "home-assistant"
        return [_FakeTool("HassTurnOn"), _FakeTool("GetLiveContext")]

    monkeypatch.setattr(mcp_tools, "MultiServerMCPClient", FakeClient)
    monkeypatch.setattr(mcp_tools, "_adapter_load_tools", fake_load_tools)

    tools = await mcp_tools.load_mcp_tools()

    tool_names = sorted(t.name for t in tools)
    assert tool_names == ["GetLiveContext", "HassTurnOn"]
    assert "HassTurnOn" in mcp_tools._MCP_TOOLS
    assert "GetLiveContext" in mcp_tools._MCP_TOOLS

    await mcp_tools.close_mcp_sessions()


@pytest.mark.asyncio
async def test_all_servers_fail_returns_empty_list(monkeypatch):
    """If every server fails, the loader still returns [] — no exception leaks."""
    from orchestrator.app import mcp_tools
    mcp_tools._MCP_TOOLS.clear()
    monkeypatch.setattr(mcp_tools, "_servers_from_env", _two_servers)

    class FakeClient:
        def __init__(self, servers): pass

        def session(self, _name):
            return _raising_session()

    monkeypatch.setattr(mcp_tools, "MultiServerMCPClient", FakeClient)

    tools = await mcp_tools.load_mcp_tools()
    assert tools == []
    assert mcp_tools._MCP_TOOLS == {}

    await mcp_tools.close_mcp_sessions()


@pytest.mark.asyncio
async def test_load_tools_failure_isolated_per_server(monkeypatch):
    """If _adapter_load_tools raises for one server, others still load."""
    from orchestrator.app import mcp_tools
    mcp_tools._MCP_TOOLS.clear()
    monkeypatch.setattr(mcp_tools, "_servers_from_env", _two_servers)

    class FakeClient:
        def __init__(self, servers): pass

        def session(self, _name):
            return _ok_session()

    async def fake_load_tools(_session, server_name):
        if server_name == "server-a":
            raise ValueError("server A tool list corrupt")
        return [_FakeTool("HassTurnOn")]

    monkeypatch.setattr(mcp_tools, "MultiServerMCPClient", FakeClient)
    monkeypatch.setattr(mcp_tools, "_adapter_load_tools", fake_load_tools)

    tools = await mcp_tools.load_mcp_tools()

    assert [t.name for t in tools] == ["HassTurnOn"]

    await mcp_tools.close_mcp_sessions()
