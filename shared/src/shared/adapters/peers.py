"""Parallel, depth-one peer consultations using cached A2A clients."""

from __future__ import annotations

import asyncio
import uuid
from collections.abc import Mapping
from datetime import date
from uuid import UUID

import httpx
from a2a.client import A2ACardResolver, Client, ClientConfig, ClientFactory
from a2a.types import AgentCard, Message, Part, Role, Task, TextPart

from shared.config.adapter_services import PeerSettings
from shared.observability.logging import get_logger

logger = get_logger(__name__)

_card_cache: dict[str, AgentCard] = {}
_client_cache: dict[str, Client] = {}
_httpx_cache: dict[str, httpx.AsyncClient] = {}
_lock = asyncio.Lock()


def _normalize(url: str) -> str:
    return url.rstrip("/")


async def _get_card(base_url: str, *, timeout: float = 10.0) -> AgentCard:
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
        logger.info("peer_card_resolved", agent=card.name)
        return card


async def _get_client(base_url: str) -> Client:
    """Return a cached a2a-sdk Client for the given base URL.

    The underlying httpx client is reused across calls to enable connection
    pooling and keep-alive. Cleared via ``clear_caches()``.
    """
    key = _normalize(base_url)
    if key in _client_cache:
        return _client_cache[key]
    card = await _get_card(key)
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


def default_peer_registry() -> dict[str, dict[str, str]]:
    settings = PeerSettings()
    return {
        name.removesuffix("_agent_url"): {"url": str(url)}
        for name, url in settings.model_dump().items()
    }


def _extract_task_text(task: Task) -> str | None:
    for art in task.artifacts or []:
        for p in art.parts or []:
            root = getattr(p, "root", p)
            text = getattr(root, "text", None)
            if text:
                return str(text)
    return None


async def call_peer(
    url: str,
    skill_id: str,
    *,
    user_id: str | None = None,
    message_text: str = "Summary requested by peer agent",
    for_date: str | None = None,
) -> str:
    """Call a peer agent's skill over A2A.

    `user_id` is propagated in Message.metadata["user_id"] when provided, so the
    remote executor can scope DB + vector queries.
    Missing user_id raises on the remote side — peer callers must supply it.

    `for_date` (ISO date string, e.g. "2026-04-30") is propagated as
    metadata["for_date"]. Peer agents that honor it (nutrition, workout) scope
    their analysis to that day instead of "today" — used when a primary agent
    needs context for a specific calendar day (e.g. sleep correlating with the
    PRIOR day's intake/training, not today's).
    """
    try:
        client = await _get_client(url)
        metadata: dict[str, object] = {"skillId": skill_id, "is_peer_call": True}
        if user_id:
            metadata["user_id"] = user_id
        if for_date:
            metadata["for_date"] = for_date
        message_with_hint = (
            f"{message_text}\n\nFocus on data for {for_date} (YYYY-MM-DD)."
            if for_date
            else message_text
        )
        message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=message_with_hint))],
            message_id=str(uuid.uuid4()),
            metadata=metadata,
        )
        async for resp in client.send_message(message):
            if isinstance(resp, tuple):
                task, _update = resp
                text = _extract_task_text(task)
                if text:
                    return str(text)
            elif isinstance(resp, Message):
                for p in resp.parts or []:
                    root = getattr(p, "root", p)
                    text = getattr(root, "text", None)
                    if text:
                        return str(text)
    except Exception as e:
        logger.warning("peer_call_failed", skill=skill_id, error_type=type(e).__name__)
    return LEGACY_UNAVAILABLE


async def fetch_peer_artifacts(
    peer_agents: dict[str, dict[str, str]],
    peer_task_names: dict[str, str],
    needed: set[str] | None = None,
    user_id: str | None = None,
    for_date: str | None = None,
) -> dict[str, str]:
    """Parallel peer calls; user_id + for_date propagate into each Message.metadata."""
    coros = {
        name: call_peer(
            info["url"],
            peer_task_names[name],
            user_id=user_id,
            for_date=for_date,
        )
        for name, info in peer_agents.items()
        if name in peer_task_names and info.get("url") and (needed is None or name in needed)
    }
    if not coros:
        return {}
    texts = await asyncio.gather(*coros.values())
    return dict(zip(coros.keys(), texts))


LEGACY_UNAVAILABLE = "(\u0434\u0430\u043d\u043d\u044b\u0435 \u043d\u0435\u0434\u043e\u0441\u0442\u0443\u043f\u043d\u044b)"
PEER_TIMEOUT_S = 20.0


class A2APeerClient:
    def __init__(self, registry: Mapping[str, str] | None = None) -> None:
        if registry is None:
            registry = {name: info["url"] for name, info in default_peer_registry().items()}
        self._registry = dict(registry)

    async def fetch_artifacts(
        self, *, user_id: UUID, wanted: Mapping[str, str], for_date: date | None = None
    ) -> dict[str, str]:
        if not wanted:
            return {}
        registry = {name: {"url": url} for name, url in self._registry.items()}
        try:
            # HTTP phase timeouts alone do not bound an active response stream.
            async with asyncio.timeout(PEER_TIMEOUT_S):
                texts = await fetch_peer_artifacts(
                    registry,
                    dict(wanted),
                    needed=set(wanted),
                    user_id=str(user_id),
                    for_date=for_date.isoformat() if for_date else None,
                )
        except Exception as exc:
            logger.warning("peer_fetch_failed", error_type=type(exc).__name__)
            return {}
        return {
            name: text
            for name, text in texts.items()
            if text and text.strip() and text != LEGACY_UNAVAILABLE
        }
