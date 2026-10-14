from shared.config import BaseServiceSettings


class BodySettings(BaseServiceSettings):
    service_name: str = "agent-body"
    body_agent_url: str = "http://agent-body:8004/"
