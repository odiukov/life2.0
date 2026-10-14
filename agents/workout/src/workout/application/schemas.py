from __future__ import annotations

import re
from typing import Literal

from pydantic import BaseModel, Field, field_validator

ActivityType = Literal[
    "running", "cycling", "walking", "swimming", "strength_training", "yoga", "hiking", "other"
]
_HHMM = re.compile(r"^([01]?\d|2[0-3]):[0-5]\d$")


class WorkoutExtraction(BaseModel):
    activity_type: ActivityType
    duration_minutes: int = Field(gt=0, le=24 * 60)
    distance_km: float | None = Field(default=None, ge=0, allow_inf_nan=False)
    effort: int | None = Field(default=None, ge=1, le=10)
    started_at: str | None = Field(
        default=None, description="24-hour HH:MM when it started, only if stated"
    )
    name: str | None = None

    @field_validator("started_at")
    @classmethod
    def _hhmm(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not _HHMM.match(value.strip()):
            raise ValueError("expected HH:MM")
        return value.strip()
