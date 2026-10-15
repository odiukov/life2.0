from __future__ import annotations

from typing import Literal

from pydantic import Field, SecretStr, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class AuthSettings(BaseSettings):
    """Flat env names, as the direct-sign-in branch introduced them."""

    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    auth_mode: Literal["oauth", "dev"] = "oauth"
    env: Literal["dev", "prod"] = "dev"
    auth_jwt_secret: SecretStr | None = None
    auth_public_url: str = ""
    auth_app_redirect_uri: str = "lifeagents://auth-callback"
    google_auth_client_id: str = ""
    google_auth_client_secret: SecretStr | None = None
    apple_auth_service_id: str = ""
    apple_auth_team_id: str = ""
    apple_auth_key_id: str = ""
    apple_auth_private_key: SecretStr | None = None
    session_check: bool = Field(
        default=True, description="Look up the session on every request (revocation)."
    )

    @model_validator(mode="after")
    def _dev_mode_is_local_only(self) -> AuthSettings:
        if self.auth_mode == "dev" and self.env != "dev":
            raise ValueError("AUTH_MODE=dev is refused when ENV=prod")
        if self.auth_jwt_secret is not None and len(self.auth_jwt_secret.get_secret_value()) < 32:
            raise ValueError("AUTH_JWT_SECRET must contain at least 32 characters")
        return self

    def secret(self) -> str | None:
        return self.auth_jwt_secret.get_secret_value() if self.auth_jwt_secret else None

    def public_url(self) -> str | None:
        value = self.auth_public_url.rstrip("/")
        return (
            value if value.startswith("https://") or value.startswith("http://localhost:") else None
        )
