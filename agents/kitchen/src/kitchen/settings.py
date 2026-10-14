from __future__ import annotations

from pydantic import Field
from shared.config import BaseServiceSettings, NotificationSettings


class KitchenSettings(BaseServiceSettings):
    service_name: str = "agent-kitchen"
    kitchen_agent_url: str = "http://agent-kitchen:8009/"
    notifications: NotificationSettings = Field(default_factory=NotificationSettings)
    digest_interval_minutes: int = Field(default=15, ge=1, le=60)
