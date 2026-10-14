"""Profile DTOs combining nutrition context with shared energy inputs."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from zoneinfo import ZoneInfo

from shared.domain.energy import BodyProfile


@dataclass(frozen=True, slots=True)
class UserProfile:
    timezone: ZoneInfo
    locale: str | None
    body: BodyProfile = field(default_factory=BodyProfile)

    @classmethod
    def default(cls) -> UserProfile:
        return cls(timezone=ZoneInfo("UTC"), locale=None)


@dataclass(frozen=True, slots=True)
class BodyComposition:
    recorded_at: datetime
    weight_kg: float | None
    body_fat_pct: float | None
    bmr_kcal: float | None
