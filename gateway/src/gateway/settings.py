from __future__ import annotations

from pydantic import Field, SecretStr, model_validator
from shared.config import BaseServiceSettings, SecretsSettings

AGENT_URLS = {
    "sleep": "http://agent-sleep:8001/",
    "workout": "http://agent-workout:8002/",
    "nutrition": "http://agent-nutrition:8003/",
    "body": "http://agent-body:8004/",
    "mood": "http://agent-mood:8005/",
    "habits": "http://agent-habits:8006/",
    "recovery": "http://agent-recovery:8007/",
    "medication": "http://agent-medication:8008/",
    "kitchen": "http://agent-kitchen:8009/",
    "finance": "http://agent-finance:8011/",
    "calendar": "http://agent-calendar:8012/",
    "home": "http://agent-home:8013/",
}
LEGACY_REDIRECT = (
    "com.googleusercontent.apps.90325200012-h74926clm7els3i32qjns4vskfurvln1:/integrations-callback"
)


class GatewaySettings(BaseServiceSettings):
    service_name: str = "orchestrator-gateway"
    agent_urls: dict[str, str] = Field(default_factory=lambda: dict(AGENT_URLS))
    kitchen_agent_url: str = "http://agent-kitchen:8009/"  # kept: sub-project 2 wiring reads it
    stt_url: str = "http://stt:8010"
    sync_url: str = "http://sync-service:8080"
    skill_timeout_s: float = Field(default=10.0, gt=0)
    # Body import may make two sequential vision calls; calendar exchanges OAuth tokens.
    body_skill_timeout_s: float = Field(default=90.0, gt=0)
    calendar_skill_timeout_s: float = Field(default=30.0, gt=0)
    stt_timeout_s: float = Field(default=40.0, gt=0)
    voice_max_bytes: int = Field(default=2_000_000, gt=0)
    upload_max_bytes: int = Field(default=20_000_000, gt=0)
    sync_trigger_concurrency: int = Field(default=4, ge=1)
    google_calendar_oauth_client_id: str = ""
    google_calendar_oauth_redirect_uri: str = LEGACY_REDIRECT
    oauth_state_secret: SecretStr | None = None

    secrets: SecretsSettings

    @model_validator(mode="after")
    def resolve_kitchen_url(self) -> GatewaySettings:
        self.agent_urls = {**AGENT_URLS, **self.agent_urls}
        if "kitchen_agent_url" in self.model_fields_set:
            self.agent_urls["kitchen"] = self.kitchen_agent_url
        else:
            self.kitchen_agent_url = self.agent_urls["kitchen"]
        return self
