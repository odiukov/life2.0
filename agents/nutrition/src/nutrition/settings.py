from __future__ import annotations

from shared.config import BaseServiceSettings


class NutritionSettings(BaseServiceSettings):
    service_name: str = "agent-nutrition"
    nutrition_agent_url: str = "http://agent-nutrition:8003/"
    sync_service_url: str | None = None
