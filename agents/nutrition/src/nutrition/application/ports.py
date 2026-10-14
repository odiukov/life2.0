from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Protocol
from uuid import UUID

from shared.domain.energy import BodyProfile

from nutrition.application.models import BodyComposition, UserProfile
from nutrition.domain.meal import Meal


class MealRepository(Protocol):
    async def add(self, user_id: UUID, meal: Meal) -> Meal:
        """Store a meal. If one with the same source and timestamp exists, shift the timestamp
        by 1 µs until it is free (two meals stated at the same minute are both real)."""
        ...

    async def between(self, user_id: UUID, start: datetime, end: datetime) -> list[Meal]:
        """Chat and Yazio meals with start <= recorded_at < end, oldest first."""
        ...

    async def recent(self, user_id: UUID, limit: int) -> list[Meal]:
        """Newest first."""
        ...


class ProfileRepository(Protocol):
    async def get(self, user_id: UUID) -> UserProfile:
        """Unknown users and unknown/missing time zones resolve to UTC defaults."""
        ...

    async def update_body_profile(
        self, user_id: UUID, changes: Mapping[str, object]
    ) -> BodyProfile:
        """Merge into the stored body profile; a None value removes that field."""
        ...


class BodyMetricsRepository(Protocol):
    async def latest(self, user_id: UUID) -> BodyComposition | None: ...


class NutritionSync(Protocol):
    async def refresh(self) -> None:
        """Best-effort: ask the sync service to pull fresh Yazio data. Never raises."""
        ...
