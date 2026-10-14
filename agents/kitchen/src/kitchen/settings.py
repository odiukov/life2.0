from __future__ import annotations

from shared.config import BaseServiceSettings


class KitchenSettings(BaseServiceSettings):
    service_name: str = "agent-kitchen"
    kitchen_agent_url: str = "http://agent-kitchen:8009/"
