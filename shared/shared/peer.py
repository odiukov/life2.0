"""Peer-agent consultation over A2A v0.2+ (SDK ClientFactory API)."""
from __future__ import annotations

import asyncio
import logging
import uuid

from a2a.types import Message, Part, Role, Task, TextPart

from .a2a_clients import get_client

logger = logging.getLogger(__name__)


def _extract_task_text(task: Task) -> str | None:
    for art in task.artifacts or []:
        for p in art.parts or []:
            root = getattr(p, "root", p)
            text = getattr(root, "text", None)
            if text:
                return text
    return None


async def call_peer(
    url: str,
    skill_id: str,
    *,
    message_text: str = "Summary requested by peer agent",
) -> str:
    try:
        client = await get_client(url)
        message = Message(
            role=Role.user,
            parts=[Part(root=TextPart(text=message_text))],
            message_id=str(uuid.uuid4()),
            metadata={"skillId": skill_id},
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
) -> dict[str, str]:
    coros = {
        name: call_peer(info["url"], peer_task_names[name])
        for name, info in peer_agents.items()
        if name in peer_task_names
        and info.get("url")
        and (needed is None or name in needed)
    }
    if not coros:
        return {}
    texts = await asyncio.gather(*coros.values())
    return dict(zip(coros.keys(), texts))
