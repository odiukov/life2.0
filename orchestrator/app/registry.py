"""Agent discovery — resolves AgentCards via A2A SDK."""
import logging
import os

import httpx

from shared.a2a_clients import get_card

logger = logging.getLogger(__name__)

_registry: dict[str, dict] = {}


async def discover_agents() -> None:
    for url in os.environ.get("AGENT_URLS", "").split(","):
        url = url.strip()
        if not url:
            continue
        try:
            card = await get_card(url)
            agent_name = card.name.replace("-agent", "")
            _registry[agent_name] = {
                "url": url,
                "card": card.model_dump(mode="json", by_alias=True),
            }
            logger.info("Discovered agent: %s at %s", agent_name, url)
        except Exception as e:
            logger.warning("Could not discover agent at %s: %s", url, e)


async def check_agent_health(agent_name: str) -> bool:
    entry = _registry.get(agent_name)
    if not entry:
        return False
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(f"{entry['url']}/health")
            return resp.status_code == 200
    except Exception:
        return False


def get_agent_url(agent_name: str) -> str | None:
    entry = _registry.get(agent_name)
    return entry["url"] if entry else None


def list_agents() -> list[str]:
    return list(_registry.keys())


def get_registry() -> dict[str, dict]:
    return _registry
