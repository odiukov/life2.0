"""Connection settings for peer consultations and vector memory."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict


class VectorSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    gemini_api_key: SecretStr | None = None


class PeerSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore")
    sleep_agent_url: str = "http://agent-sleep:8001/"
    workout_agent_url: str = "http://agent-workout:8002/"
    nutrition_agent_url: str = "http://agent-nutrition:8003/"
    body_agent_url: str = "http://agent-body:8004/"
    mood_agent_url: str = "http://agent-mood:8005/"
    habits_agent_url: str = "http://agent-habits:8006/"
    recovery_agent_url: str = "http://agent-recovery:8007/"
    medication_agent_url: str = "http://agent-medication:8008/"
