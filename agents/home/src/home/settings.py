from pydantic import Field
from shared.config import BaseServiceSettings, SecretsSettings


class HomeSettings(BaseServiceSettings):
    service_name: str = "agent-home"
    home_agent_url: str = "http://agent-home:8013/"
    secrets: SecretsSettings
    ask_timeout_s: float = Field(default=45.0, gt=0)
    mcp_connect_timeout_s: float = Field(default=10.0, gt=0)
    mcp_session_ttl_s: float = Field(default=600.0, gt=0)
