"""Typed service settings. The only place in new code that reads the environment.

Build settings once in service composition and pass them to consumers.
Legacy vector adapters and OTEL/Traceloop retain their env configuration for now.
"""

from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import (
    AnyHttpUrl,
    BaseModel,
    ConfigDict,
    Field,
    SecretStr,
    field_validator,
    model_validator,
)
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict

from shared.config.locales import find_locales_dir
from shared.ports.llm import LLMTask

Provider = Literal["anthropic", "openrouter", "gemini", "groq", "ollama", "claude_sdk", "fake"]
DatabaseRole = Literal["app_owner", "app_rw", "app_legacy"]


class LLMRoute(BaseModel):
    model_config = ConfigDict(frozen=True)

    provider: Provider
    model: str = Field(min_length=1)

    @model_validator(mode="before")
    @classmethod
    def _parse(cls, value: object) -> object:
        if isinstance(value, str):
            provider, sep, model = value.partition(":")
            if not sep or not model:
                raise ValueError("expected '<provider>:<model>'")
            return {"provider": provider, "model": model}
        return value

    def __str__(self) -> str:
        return f"{self.provider}:{self.model}"


class LLMSettings(BaseModel):
    # Routes use the scalar provider:model syntax rather than nested JSON decoding.
    default: Annotated[LLMRoute, NoDecode] = LLMRoute(
        provider="openrouter", model="qwen/qwen3-coder-480b-a35b-instruct:free"
    )
    tasks: dict[LLMTask, LLMRoute] = Field(default_factory=dict)
    # oauth_token sends a Claude subscription token outside Anthropic's API terms.
    anthropic_auth: Literal["api_key", "oauth_token"] = "api_key"
    timeout_s: float = Field(default=60.0, gt=0)
    retry_attempts: int = Field(default=3, ge=1)

    def route(self, task: LLMTask) -> LLMRoute:
        return self.tasks.get(task, self.default)


class DatabaseSettings(BaseModel):
    dsn: SecretStr
    role: DatabaseRole = "app_rw"
    pool_size: int = Field(default=5, ge=1)

    @field_validator("dsn", mode="before")
    @classmethod
    def _asyncpg_driver(cls, value: object) -> object:
        raw = value.get_secret_value() if isinstance(value, SecretStr) else value
        if isinstance(raw, str) and raw.startswith("postgresql://"):
            return "postgresql+asyncpg://" + raw.removeprefix("postgresql://")
        return raw


class TelemetrySettings(BaseModel):
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    log_format: Literal["json", "console"] = "json"


class BaseServiceSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_nested_delimiter="__", extra="ignore", case_sensitive=False
    )

    service_name: str = "life-agents"
    database: DatabaseSettings
    llm: LLMSettings = Field(default_factory=LLMSettings)
    telemetry: TelemetrySettings = Field(default_factory=TelemetrySettings)
    qdrant_url: AnyHttpUrl = AnyHttpUrl("http://localhost:6333")
    default_locale: Literal["ru", "en"] = "ru"
    i18n_locales_dir: Path = Field(default_factory=find_locales_dir)
    anthropic_api_key: SecretStr | None = None
    openrouter_api_key: SecretStr | None = None
    gemini_api_key: SecretStr | None = None
    groq_api_key: SecretStr | None = None
    ollama_host: str = "http://localhost:11434"
