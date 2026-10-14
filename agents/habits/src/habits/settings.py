from shared.config import BaseServiceSettings


class HabitsSettings(BaseServiceSettings):
    service_name: str = "agent-habits"
    habits_agent_url: str = "http://agent-habits:8006/"
