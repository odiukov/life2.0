"""Tests for orchestrator MCP tool discovery."""
import pytest
from unittest.mock import AsyncMock, patch


@pytest.mark.asyncio
async def test_load_mcp_tools_returns_empty_when_no_servers_configured(monkeypatch):
    """With no MCP_*_URL env vars set, loader returns []."""
    monkeypatch.delenv("MCP_GOOGLE_CALENDAR_URL", raising=False)
    from orchestrator.app.mcp_tools import load_mcp_tools, _MCP_TOOLS
    _MCP_TOOLS.clear()
    tools = await load_mcp_tools()
    assert tools == []


@pytest.mark.asyncio
async def test_load_mcp_tools_returns_discovered_tools(monkeypatch):
    """With MCP_GOOGLE_CALENDAR_URL set, loader calls MultiServerMCPClient and returns its tools."""
    monkeypatch.setenv("MCP_GOOGLE_CALENDAR_URL", "http://calendar-mcp:3000")
    monkeypatch.setenv("MCP_GOOGLE_CALENDAR_TRANSPORT", "streamable_http")

    fake_tool = type("T", (), {"name": "list-events"})()  # minimal stand-in

    class FakeClient:
        last_servers = None
        def __init__(self, servers):
            FakeClient.last_servers = servers
        async def get_tools(self):
            return [fake_tool]

    with patch("orchestrator.app.mcp_tools.MultiServerMCPClient", FakeClient):
        from orchestrator.app import mcp_tools
        mcp_tools._MCP_TOOLS.clear()
        tools = await mcp_tools.load_mcp_tools()

    assert len(tools) == 1
    assert tools[0] is fake_tool
    assert "google-calendar" in FakeClient.last_servers
    assert FakeClient.last_servers["google-calendar"]["url"] == "http://calendar-mcp:3000"
    assert FakeClient.last_servers["google-calendar"]["transport"] == "streamable_http"


@pytest.mark.asyncio
async def test_load_mcp_tools_swallows_errors_and_returns_empty(monkeypatch):
    """If MultiServerMCPClient raises (e.g. server down), loader returns []."""
    monkeypatch.setenv("MCP_GOOGLE_CALENDAR_URL", "http://calendar-mcp:3000")

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
    monkeypatch.setenv("MCP_GOOGLE_CALENDAR_URL", "http://calendar-mcp:3000")

    class FakeTool:
        def __init__(self, name): self.name = name

    class FakeClient:
        def __init__(self, servers): pass
        async def get_tools(self):
            return [FakeTool("list-events"), FakeTool("create-event")]

    with patch("orchestrator.app.mcp_tools.MultiServerMCPClient", FakeClient):
        from orchestrator.app import mcp_tools
        mcp_tools._MCP_TOOLS.clear()
        await mcp_tools.load_mcp_tools()

    assert "list-events" in mcp_tools._MCP_TOOLS
    assert "create-event" in mcp_tools._MCP_TOOLS
    assert mcp_tools._MCP_TOOLS["list-events"].name == "list-events"


def test_get_mcp_tool_returns_none_for_unknown_name():
    from orchestrator.app import mcp_tools
    mcp_tools._MCP_TOOLS.clear()
    assert mcp_tools.get_mcp_tool("nonexistent-tool") is None
