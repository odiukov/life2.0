# shared/shared/peer.py
"""Utilities for peer-agent consultation used by all agents."""
import asyncio
import logging

import httpx

logger = logging.getLogger(__name__)


async def call_peer(url: str, task_name: str) -> str:
    """POST to a peer agent's /tasks endpoint, return artifact text."""
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                f"{url}/tasks",
                json={"task": task_name, "params": {"context": "summary requested by peer-agent"}},
            )
            resp.raise_for_status()
            data = resp.json()
            artifacts = data.get("artifacts", [])
            if artifacts and artifacts[0].get("parts"):
                return artifacts[0]["parts"][0].get("text", "(данные недоступны)")
    except Exception as e:
        logger.warning("Peer call to %s/%s failed: %s", url, task_name, e)
    return "(данные недоступны)"


async def fetch_peer_artifacts(
    peer_agents: dict,
    peer_task_names: dict[str, str],
    needed: set[str] | None = None,
) -> dict[str, str]:
    """Call selected peer agents in parallel, return {name: text}.

    Args:
        peer_agents: dict of {name: {url, card}} passed in request params.
        peer_task_names: mapping of peer name → task to call (agent-specific).
        needed: set of peer names to consult. None = all known peers, empty set = skip all.
    """
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
