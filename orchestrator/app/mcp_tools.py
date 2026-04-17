"""MCP tool discovery for the orchestrator.

Discovers tools from configured MCP servers at orchestrator startup and exposes
them as LangChain BaseTool instances. Maintains a name-indexed cache so
briefing-side helpers can look up specific tools without re-discovering.

Failure semantics: never raises. A missing env var, unreachable server, or
parse failure returns an empty list and leaves the cache empty. This keeps the
orchestrator bootable even when an MCP server is down.
"""
from __future__ import annotations

import logging
import os

from langchain_core.tools import BaseTool
from langchain_mcp_adapters.client import MultiServerMCPClient

logger = logging.getLogger(__name__)

# Module-level cache populated by load_mcp_tools() on orchestrator startup.
# Keyed by tool.name (as emitted by the MCP server).
_MCP_TOOLS: dict[str, BaseTool] = {}


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
    """Discover MCP tools. Populates _MCP_TOOLS cache. Never raises."""
    servers = _servers_from_env()
    if not servers:
        logger.info("No MCP servers configured — skipping tool discovery")
        return []

    try:
        client = MultiServerMCPClient(servers)
        tools = await client.get_tools()
    except Exception as e:
        logger.warning("MCP tool discovery failed: %s", e)
        return []

    for t in tools:
        _MCP_TOOLS[t.name] = t
    logger.info("Loaded %d MCP tools: %s", len(tools), [t.name for t in tools])
    return tools


def get_mcp_tool(name: str) -> BaseTool | None:
    """Look up a previously-discovered MCP tool by name. Returns None if absent."""
    return _MCP_TOOLS.get(name)
