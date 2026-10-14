from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class SttSettings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="STT__", extra="ignore")

    model: str = "large-v3-turbo"
    compute_type: str = "int8"
    device: str = "cpu"
    model_dir: str = "/models"
    max_bytes: int = Field(default=2_000_000, gt=0)
    max_duration_s: float = Field(default=60.0, gt=0)
    queue_timeout_s: float = Field(default=30.0, gt=0)
