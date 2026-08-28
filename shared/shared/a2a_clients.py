"""Cached A2A Client + AgentCard resolution shared by orchestrator and peer paths.

Uses the a2a-sdk 0.3.x ClientFactory API — the deprecated A2AClient is avoided.
Consumers call ``await get_client(url)`` to get a ready ``Client`` and then
iterate ``client.send_message(message)`` for responses.
"""
from __future__ import annotations

import asyncio
import logging

import httpx
from a2a.client import A2ACardResolver, Client, ClientConfig, ClientFactory
from a2a.types import AgentCard

logger = logging.getLogger(__name__)

_card_cache: dict[str, AgentCard] = {}
_client_cache: dict[str, Client] = {}
_httpx_cache: dict[str, httpx.AsyncClient] = {}
_lock = asyncio.Lock()


def _normalize(url: str) -> str:
    return url.rstrip("/")


async def get_card(base_url: str, *, timeout: float = 10.0) -> AgentCard:
    """Fetch the AgentCard once per base URL and cache it."""
    key = _normalize(base_url)
    if key in _card_cache:
        return _card_cache[key]
    async with _lock:
        if key in _card_cache:
            return _card_cache[key]
        async with httpx.AsyncClient(timeout=timeout) as httpx_client:
            resolver = A2ACardResolver(httpx_client=httpx_client, base_url=key)
            card = await resolver.get_agent_card()
        _card_cache[key] = card
        logger.info("Resolved AgentCard for %s -> %s", key, card.name)
        return card


async def get_client(base_url: str) -> Client:
    """Return a cached a2a-sdk Client for the given base URL.

    The underlying httpx client is reused across calls to enable connection
    pooling and keep-alive. Cleared via ``clear_caches()``.
    """
    key = _normalize(base_url)
    if key in _client_cache:
        return _client_cache[key]
    card = await get_card(key)
    async with _lock:
        if key in _client_cache:
            return _client_cache[key]
        httpx_client = _httpx_cache.get(key)
        if httpx_client is None:
            httpx_client = httpx.AsyncClient(timeout=180.0)
            _httpx_cache[key] = httpx_client
        config = ClientConfig(httpx_client=httpx_client, streaming=True)
        factory = ClientFactory(config)
        client = factory.create(card)
        _client_cache[key] = client
        return client


def clear_caches() -> None:
    """Testing utility — drop all cached cards and clients."""
    _card_cache.clear()
    _client_cache.clear()
    _httpx_cache.clear()
