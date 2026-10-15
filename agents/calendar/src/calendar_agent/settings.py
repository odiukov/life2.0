from pydantic import SecretStr
from shared.config import BaseServiceSettings, SecretsSettings

LEGACY_REDIRECT = (
    "com.googleusercontent.apps.90325200012-h74926clm7els3i32qjns4vskfurvln1:/integrations-callback"
)


class CalendarSettings(BaseServiceSettings):
    service_name: str = "agent-calendar"
    calendar_agent_url: str = "http://agent-calendar:8012/"
    secrets: SecretsSettings
    # Same environment names the legacy orchestrator read, so existing .env files keep working.
    google_calendar_oauth_client_id: str = ""
    google_calendar_oauth_client_secret: SecretStr | None = None
    google_calendar_oauth_redirect_uri: str = LEGACY_REDIRECT
