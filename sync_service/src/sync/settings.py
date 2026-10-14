from __future__ import annotations

from pydantic import BaseModel, Field, SecretStr
from shared.config import BaseServiceSettings, SecretsSettings


class SyncOptions(BaseModel):
    hour: int = Field(default=9, ge=0, le=23)
    interval_minutes: int = Field(default=15, ge=1)
    manual_cooldown_minutes: int = Field(default=10, ge=0)
    garmin_days: int = Field(default=7, ge=1, le=30)
    yazio_days: int = Field(default=2, ge=1, le=30)
    yazio_client_id: SecretStr | None = None
    yazio_client_secret: SecretStr | None = None

    @property
    def yazio_enabled(self) -> bool:
        return bool(self.yazio_client_id and self.yazio_client_secret)


class SyncServiceSettings(BaseServiceSettings):
    service_name: str = "sync-service"
    secrets: SecretsSettings
    sync: SyncOptions = SyncOptions()
