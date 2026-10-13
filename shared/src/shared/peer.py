"""Peer-agent consultation over A2A v0.2+ (SDK ClientFactory API)."""
from __future__ import annotations

import asyncio
import logging
import os
import uuid

from a2a.types import Message, Part, Role, Task, TextPart

from .a2a_clients import get_client

logger = logging.getLogger(__name__)

# Default URLs match docker-compose service names + ports. Each peer container
# overrides via <NAME>_AGENT_URL when present (see docker-compose.yml).
_DEFAULT_PEER_URLS: dict[str, str] = {
    "sleep": "http://agent-sleep:8001/",
    "workout": "http://agent-workout:8002/",
    "nutrition": "http://agent-nutrition:8003/",
    "body": "http://agent-body:8004/",
    "mood": "http://agent-mood:8005/",
    "habits": "http://agent-habits:8006/",
    "recovery": "http://agent-recovery:8007/",
    "medication": "http://agent-medication:8008/",
}


def default_peer_registry() -> dict[str, dict[str, str]]:
    """Build a `{name: {"url": str}}` registry from `<NAME>_AGENT_URL` env vars,
    falling back to the docker-compose service URLs. Used by peer executors
    that need to consult other agents — keeps the registry derivation in one
    place so empty `{}` regressions can't reappear silently."""
    out: dict[str, dict[str, str]] = {}
    for name, default in _DEFAULT_PEER_URLS.items():
        url = os.environ.get(f"{name.upper()}_AGENT_URL", default)
        out[name] = {"url": url}
    return out


def _extract_task_text(task: Task) -> str | None:
    for art in task.artifacts or []:
        for p in art.parts or []:
            root = getattr(p, "root", p)
            text = getattr(root, "text", None)
            if text:
                return text
    return None


def is_peer_call_from_metadata(metadata: dict | None) -> bool:
    """Return True iff the inbound A2A message was issued by another peer agent
    via call_peer(). Receiving executors use this to skip their own
    peer-consult step — enforcing a hard depth-1 cap on fan-out.

    Strict equality with True (not truthiness) so wire-level string 'true'
    or stale flags don't accidentally activate the short-circuit."""
    if not isinstance(metadata, dict):
        return False
    return metadata.get("is_peer_call") is True


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
        client = await get_client(url)
        metadata: dict[str, object] = {"skillId": skill_id, "is_peer_call": True}
        if user_id:
            metadata["user_id"] = user_id
        if for_date:
            metadata["for_date"] = for_date
        message_with_hint = (
            f"{message_text}\n\nFocus on data for {for_date} (YYYY-MM-DD)."
            if for_date else message_text
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
                    return text
            elif isinstance(resp, Message):
                for p in resp.parts or []:
                    root = getattr(p, "root", p)
                    text = getattr(root, "text", None)
                    if text:
                        return text
    except Exception as e:
        logger.warning("Peer call to %s/%s failed: %s", url, skill_id, e)
    return "(данные недоступны)"


async def fetch_peer_artifacts(
    peer_agents: dict,
    peer_task_names: dict[str, str],
    needed: set[str] | None = None,
    user_id: str | None = None,
    for_date: str | None = None,
) -> dict[str, str]:
    """Parallel peer calls; user_id + for_date propagate into each Message.metadata."""
    coros = {
        name: call_peer(
            info["url"], peer_task_names[name],
            user_id=user_id, for_date=for_date,
        )
        for name, info in peer_agents.items()
        if name in peer_task_names
        and info.get("url")
        and (needed is None or name in needed)
    }
    if not coros:
        return {}
    texts = await asyncio.gather(*coros.values())
    return dict(zip(coros.keys(), texts))
