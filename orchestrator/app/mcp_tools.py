"""MCP tool discovery for the orchestrator.

Opens long-lived MCP sessions at startup and loads LangChain tools bound to
those sessions. Tools reuse the persistent session for every invocation, which
avoids servers that allow only one session per process.

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
import asyncio
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
    ha_base = os.environ.get("HA_BASE_URL")
    ha_token = os.environ.get("HA_TOKEN")
    if ha_base and ha_token:
        servers["home-assistant"] = {
            "url": f"{ha_base.rstrip('/')}/mcp_server/sse",
            "transport": "sse",
            "headers": {"Authorization": f"Bearer {ha_token}"},
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
    except Exception as e:
        logger.warning("MCP client init failed: %s", e)
        return []

    for server_name in servers:
        try:
            session = await stack.enter_async_context(client.session(server_name))
            tools = await _adapter_load_tools(session, server_name=server_name)
            all_tools.extend(tools)
        except Exception as e:
            logger.warning("MCP server '%s' discovery failed: %s", server_name, e)
            continue

    if not all_tools:
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
    if _session_stack is not None:
        try:
            await _session_stack.aclose()
        except Exception as e:
            logger.warning("Error closing MCP sessions: %s", e)
    _session_stack = None
    _MCP_TOOLS.clear()
    stacks = list(_USER_MCP_STACKS.values())
    _USER_MCP_STACKS.clear()
    _USER_MCP_CACHE.clear()
    for stack in stacks:
        try:
            await stack.aclose()
        except Exception as e:
            logger.warning("Error closing per-user MCP session: %s", e)


def get_mcp_tool(name: str) -> BaseTool | None:
    """Look up a previously-discovered MCP tool by name. Returns None if absent."""
    return _MCP_TOOLS.get(name)


# ---------------------------------------------------------------------------
# Per-user MCP (Task 17)
#
# Each user's MCP surface depends on what they've connected:
#   - HA MCP: creds in vault under service='ha' (base_url + token)
#
# Tools are cached per user_id for 10 minutes to amortize the MCP handshake.
# ---------------------------------------------------------------------------

from time import monotonic
from uuid import UUID

_USER_MCP_CACHE: dict[str, tuple[float, list[BaseTool]]] = {}
_USER_MCP_STACKS: dict[str, AsyncExitStack] = {}
_USER_MCP_TTL_SECONDS = 600
_USER_MCP_MAX_ENTRIES = 128


def _close_stack_soon(stack: AsyncExitStack | None) -> None:
    if stack is None:
        return
    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        asyncio.run(stack.aclose())
    else:
        loop.create_task(stack.aclose())


async def _build_user_servers(user_id: UUID) -> dict[str, dict]:
    """Assemble the MCP server config dict for a single user from the vault."""
    from . import vault

    servers: dict[str, dict] = {}

    ha_creds = await vault.get(user_id, "ha")
    if ha_creds:
        servers["home-assistant"] = {
            "url": f"{ha_creds['base_url'].rstrip('/')}/mcp_server/sse",
            "transport": "sse",
            "headers": {"Authorization": f"Bearer {ha_creds['token']}"},
        }

    return servers


async def _build_tools_for_user(user_id: UUID) -> list[BaseTool]:
    """Discover MCP tools for the given user. Never raises."""
    servers = await _build_user_servers(user_id)
    if not servers:
        return []

    try:
        client = MultiServerMCPClient(servers)
    except Exception as e:
        logger.warning("per-user MCP client init failed (user=%s): %s", user_id, e)
        return []

    collected: list[BaseTool] = []
    stack = AsyncExitStack()
    for server_name in servers:
        try:
            session = await stack.enter_async_context(client.session(server_name))
            tools = await _adapter_load_tools(session, server_name=server_name)
            collected.extend(tools)
        except Exception as e:
            logger.warning(
                "per-user MCP server '%s' discovery failed (user=%s): %s",
                server_name, user_id, e,
            )
            continue
    key = str(user_id)
    if collected:
        old_stack = _USER_MCP_STACKS.pop(key, None)
        _close_stack_soon(old_stack)
        _USER_MCP_STACKS[key] = stack
    else:
        await stack.aclose()
    return collected


async def get_user_mcp_tools(user_id: UUID) -> list[BaseTool]:
    """Return MCP tools for the given user, per connected services.

    Cached for 10 minutes per user_id. Entries evicted once the cache exceeds
    128 users to cap memory. Never raises — returns `[]` on any failure.
    """
    key = str(user_id)
    now = monotonic()
    entry = _USER_MCP_CACHE.get(key)
    if entry is not None and (now - entry[0]) < _USER_MCP_TTL_SECONDS:
        return entry[1]
    if entry is not None:
        _USER_MCP_CACHE.pop(key, None)
        _close_stack_soon(_USER_MCP_STACKS.pop(key, None))

    tools = await _build_tools_for_user(user_id)

    if len(_USER_MCP_CACHE) >= _USER_MCP_MAX_ENTRIES:
        # Evict the oldest entry (by insertion order)
        oldest = next(iter(_USER_MCP_CACHE))
        _USER_MCP_CACHE.pop(oldest, None)
        _close_stack_soon(_USER_MCP_STACKS.pop(oldest, None))
    _USER_MCP_CACHE[key] = (now, tools)
    return tools


def invalidate_user_mcp_cache(user_id: UUID) -> None:
    """Drop a user's cached tools — call after (dis)connecting an integration."""
    key = str(user_id)
    _USER_MCP_CACHE.pop(key, None)
    _close_stack_soon(_USER_MCP_STACKS.pop(key, None))
