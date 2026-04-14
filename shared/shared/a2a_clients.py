"""Cached A2AClient + AgentCard resolution shared by orchestrator and peer-to-peer paths."""
from __future__ import annotations

import asyncio
import logging

import httpx
from a2a.client import A2AClient, A2ACardResolver
from a2a.types import AgentCard

logger = logging.getLogger(__name__)

_card_cache: dict[str, AgentCard] = {}
_client_cache: dict[str, A2AClient] = {}
_lock = asyncio.Lock()


def _normalize(url: str) -> str:
    return url.rstrip("/")


async def get_card(base_url: str, *, timeout: float = 10.0) -> AgentCard:
    """Fetch the AgentCard once per base URL and cache it."""
    key = _normalize(base_url)
    if key in _card_cache:
        return _card_cache[key]
    async with _lock:
        if key in _card_cache:  # re-check after acquiring lock
            return _card_cache[key]
        async with httpx.AsyncClient(timeout=timeout) as httpx_client:
            resolver = A2ACardResolver(httpx_client=httpx_client, base_url=key)
            card = await resolver.get_agent_card()
        _card_cache[key] = card
        logger.info("Resolved AgentCard for %s -> %s", key, card.name)
        return card


async def get_client(base_url: str) -> A2AClient:
    """Return a cached A2AClient for the given base URL, resolving the card if needed."""
    key = _normalize(base_url)
    if key in _client_cache:
        return _client_cache[key]
    card = await get_card(key)
    async with _lock:
        if key in _client_cache:
            return _client_cache[key]
        httpx_client = httpx.AsyncClient(timeout=180.0)
        client = A2AClient(httpx_client=httpx_client, agent_card=card)
        _client_cache[key] = client
        return client


def clear_caches() -> None:
    """Testing utility — drop all cached cards and clients."""
    _card_cache.clear()
    _client_cache.clear()
