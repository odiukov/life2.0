from __future__ import annotations

from pydantic import Field
from shared.config import BaseServiceSettings


class GatewaySettings(BaseServiceSettings):
    service_name: str = "orchestrator-gateway"
    kitchen_agent_url: str = "http://agent-kitchen:8009/"
    stt_url: str = "http://stt:8010"
    skill_timeout_s: float = Field(default=10.0, gt=0)
    stt_timeout_s: float = Field(default=40.0, gt=0)
    voice_max_bytes: int = Field(default=2_000_000, gt=0)
