from shared.config import BaseServiceSettings


class SleepSettings(BaseServiceSettings):
    service_name: str = "agent-sleep"
    sleep_agent_url: str = "http://agent-sleep:8001/"
