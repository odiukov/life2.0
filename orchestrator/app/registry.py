import httpx
import os
import logging

from .router import INTENT_KEYWORDS

logger = logging.getLogger(__name__)

_registry: dict[str, dict] = {}


async def discover_agents() -> None:
    """Query all configured agent URLs for their Agent Cards."""
    agent_urls = os.environ.get("AGENT_URLS", "").split(",")

    for url in agent_urls:
        url = url.strip()
        if not url:
            continue
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{url}/.well-known/agent.json")
                resp.raise_for_status()
                card = resp.json()
                agent_name = card["name"].replace("-agent", "")
                if agent_name not in INTENT_KEYWORDS:
                    logger.warning(
                        f"Agent '{card['name']}' produces key '{agent_name}' "
                        f"which is not in known intents {list(INTENT_KEYWORDS.keys())}. "
                        f"It may not be routable by the classifier."
                    )
                _registry[agent_name] = {"url": url, "card": card}
                logger.info(f"Discovered agent: {agent_name} at {url}")
        except Exception as e:
            logger.warning(f"Could not discover agent at {url}: {e}")


def get_agent_url(agent_name: str) -> str | None:
    entry = _registry.get(agent_name)
    return entry["url"] if entry else None


def list_agents() -> list[str]:
    return list(_registry.keys())
