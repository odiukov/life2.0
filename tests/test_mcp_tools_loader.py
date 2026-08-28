"""Tests for orchestrator MCP tool discovery."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_load_mcp_tools_returns_empty_when_no_servers_configured(monkeypatch):
    """With no MCP_*_URL env vars set, loader returns []."""
    monkeypatch.delenv("HA_BASE_URL", raising=False)
    monkeypatch.delenv("HA_TOKEN", raising=False)
    from orchestrator.app.mcp_tools import load_mcp_tools, _MCP_TOOLS
    _MCP_TOOLS.clear()
    tools = await load_mcp_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_load_mcp_tools_returns_discovered_tools(monkeypatch):
    """With HA env set, loader opens a session per server and feeds it to
    _adapter_load_tools."""
    monkeypatch.setenv("HA_BASE_URL", "http://ha.example")
    monkeypatch.setenv("HA_TOKEN", "tok")

    fake_tool = type("T", (), {"name": "HassTurnOn"})()  # minimal stand-in

    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return False

    class FakeClient:
        last_servers = None
        def __init__(self, servers):
            FakeClient.last_servers = servers
        def session(self, name):
            return _FakeSession()

    async def fake_load(session, server_name=None):
        return [fake_tool]

    with patch("orchestrator.app.mcp_tools.MultiServerMCPClient", FakeClient), \
         patch("orchestrator.app.mcp_tools._adapter_load_tools", new=fake_load):
        from orchestrator.app import mcp_tools
        mcp_tools._MCP_TOOLS.clear()
        await mcp_tools.close_mcp_sessions()
        tools = await mcp_tools.load_mcp_tools()

    assert len(tools) == 1
    assert tools[0] is fake_tool
    assert "home-assistant" in FakeClient.last_servers
    assert FakeClient.last_servers["home-assistant"]["url"] == "http://ha.example/mcp_server/sse"
    assert FakeClient.last_servers["home-assistant"]["transport"] == "sse"

    await mcp_tools.close_mcp_sessions()


@pytest.mark.asyncio
async def test_load_mcp_tools_swallows_errors_and_returns_empty(monkeypatch):
    """If MultiServerMCPClient raises (e.g. server down), loader returns []."""
    monkeypatch.setenv("HA_BASE_URL", "http://ha.example")
    monkeypatch.setenv("HA_TOKEN", "tok")

    class FakeClient:
        def __init__(self, servers):
            pass
        async def get_tools(self):
            raise RuntimeError("server unreachable")

    with patch("orchestrator.app.mcp_tools.MultiServerMCPClient", FakeClient):
        from orchestrator.app import mcp_tools
        mcp_tools._MCP_TOOLS.clear()
        tools = await mcp_tools.load_mcp_tools()

    assert tools == []


@pytest.mark.asyncio
async def test_load_mcp_tools_caches_by_name(monkeypatch):
    """After a successful load, tools are indexed by `.name` in the module cache."""
    monkeypatch.setenv("HA_BASE_URL", "http://ha.example")
    monkeypatch.setenv("HA_TOKEN", "tok")

    class FakeTool:
        def __init__(self, name): self.name = name

    class _FakeSession:
        async def __aenter__(self): return self
        async def __aexit__(self, *exc): return False

    class FakeClient:
        def __init__(self, servers): pass
        def session(self, name): return _FakeSession()

    async def fake_load(session, server_name=None):
        return [FakeTool("HassTurnOn"), FakeTool("GetLiveContext")]

    with patch("orchestrator.app.mcp_tools.MultiServerMCPClient", FakeClient), \
         patch("orchestrator.app.mcp_tools._adapter_load_tools", new=fake_load):
        from orchestrator.app import mcp_tools
        mcp_tools._MCP_TOOLS.clear()
        await mcp_tools.close_mcp_sessions()
        await mcp_tools.load_mcp_tools()

    assert "HassTurnOn" in mcp_tools._MCP_TOOLS
    assert "GetLiveContext" in mcp_tools._MCP_TOOLS
    assert mcp_tools._MCP_TOOLS["HassTurnOn"].name == "HassTurnOn"

    await mcp_tools.close_mcp_sessions()


def test_get_mcp_tool_returns_none_for_unknown_name():
    from orchestrator.app import mcp_tools
    mcp_tools._MCP_TOOLS.clear()
    assert mcp_tools.get_mcp_tool("nonexistent-tool") is None
