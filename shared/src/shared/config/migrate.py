"""Settings for role bootstrap and schema migration."""

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict
from sqlalchemy.engine import URL

from shared.schema.roles import RolePasswords


class MigrateSettings(BaseSettings):
    model_config = SettingsConfigDict(extra="ignore", case_sensitive=False)

    postgres_host: str = "postgres"
    postgres_port: int = 5432
    postgres_db: str
    postgres_user: str
    postgres_password: SecretStr
    app_owner_password: SecretStr
    app_rw_password: SecretStr

    def url(self, user: str, password: SecretStr) -> str:
        return URL.create(
            "postgresql+asyncpg",
            username=user,
            password=password.get_secret_value(),
            host=self.postgres_host,
            port=self.postgres_port,
            database=self.postgres_db,
        ).render_as_string(hide_password=False)

    def passwords(self) -> RolePasswords:
        return RolePasswords(
            owner=self.app_owner_password.get_secret_value(),
            rw=self.app_rw_password.get_secret_value(),
        )
