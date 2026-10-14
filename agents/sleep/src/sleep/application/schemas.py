from __future__ import annotations

import re

from pydantic import BaseModel, Field, field_validator

_HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


class SleepExtraction(BaseModel):
    duration_minutes: int | None = Field(default=None, gt=0, le=24 * 60)
    bed_time: str | None = Field(
        default=None, description="24-hour HH:MM when the person fell asleep"
    )
    wake_time: str | None = Field(default=None, description="24-hour HH:MM when the person woke up")
    quality: int | None = Field(default=None, ge=1, le=5)
    note: str | None = None

    @field_validator("bed_time", "wake_time")
    @classmethod
    def _hhmm(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HHMM.match(value.strip()):
            raise ValueError("expected HH:MM")
        return value.strip()
