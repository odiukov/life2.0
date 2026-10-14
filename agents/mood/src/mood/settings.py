from shared.config import BaseServiceSettings


class MoodSettings(BaseServiceSettings):
    service_name: str = "agent-mood"
    mood_agent_url: str = "http://agent-mood:8005/"
