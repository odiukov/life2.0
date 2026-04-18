"""MCP tool discovery for the orchestrator.

Opens long-lived MCP sessions at startup and loads LangChain tools bound to
those sessions. Tools reuse the persistent session for every invocation, which
avoids servers that allow only one session per process (e.g.
nspady/google-calendar-mcp v2.6.1 in HTTP mode).

Pair load_mcp_tools() at startup with close_mcp_sessions() at shutdown so the
sessions close cleanly on lifespan exit.

Failure semantics: never raises. A missing env var, unreachable server, or
parse failure returns an empty list, closes any half-open sessions, and leaves
the cache empty — keeps the orchestrator bootable even when an MCP server is
down.
"""
from __future__ import annotations

import logging
import os
from contextlib import AsyncExitStack

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient
from langchain_mcp_adapters.tools import load_mcp_tools as _adapter_load_tools

logger = logging.getLogger(__name__)

# Module-level cache populated by load_mcp_tools() on orchestrator startup.
# Keyed by tool.name (as emitted by the MCP server).
_MCP_TOOLS: dict[str, BaseTool] = {}

# Holds the open session contexts for the lifetime of the orchestrator. Tools
# returned from load_mcp_tools() reference sessions inside this stack, so it
# must stay alive until close_mcp_sessions() is called.
_session_stack: AsyncExitStack | None = None


def _servers_from_env() -> dict[str, dict]:
    """Build MultiServerMCPClient config from env. Extensible for future MCPs."""
    servers: dict[str, dict] = {}
    if url := os.environ.get("MCP_GOOGLE_CALENDAR_URL"):
        servers["google-calendar"] = {
            "url": url,
            "transport": os.environ.get("MCP_GOOGLE_CALENDAR_TRANSPORT", "streamable_http"),
        }
    # Future: MCP_GMAIL_URL, MCP_GITHUB_URL, etc. added here.
    return servers


async def load_mcp_tools() -> list[BaseTool]:
    """Open persistent MCP sessions and return tools bound to them.

    Idempotent: subsequent calls return the cached tool list without reopening
    sessions. Never raises.
    """
    global _session_stack

    if _MCP_TOOLS:
        return list(_MCP_TOOLS.values())

    servers = _servers_from_env()
    if not servers:
        logger.info("No MCP servers configured — skipping tool discovery")
        return []

    stack = AsyncExitStack()
    all_tools: list[BaseTool] = []
    try:
        client = MultiServerMCPClient(servers)
        for server_name in servers:
            session = await stack.enter_async_context(client.session(server_name))
            tools = await _adapter_load_tools(session, server_name=server_name)
            all_tools.extend(tools)
    except Exception as e:
        logger.warning("MCP tool discovery failed: %s", e)
        await stack.aclose()
        return []

    _session_stack = stack
    for t in all_tools:
        _MCP_TOOLS[t.name] = t
    logger.info("Loaded %d MCP tools: %s", len(all_tools), [t.name for t in all_tools])
    return all_tools


async def close_mcp_sessions() -> None:
    """Close all persistent MCP sessions. Call once on app shutdown."""
    global _session_stack
    if _session_stack is None:
        return
    try:
        await _session_stack.aclose()
    except Exception as e:
        logger.warning("Error closing MCP sessions: %s", e)
    _session_stack = None
    _MCP_TOOLS.clear()


def get_mcp_tool(name: str) -> BaseTool | None:
    """Look up a previously-discovered MCP tool by name. Returns None if absent."""
    return _MCP_TOOLS.get(name)
