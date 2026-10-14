"""In-memory repositories with the same contract as the SQL ones (see tests/contract)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

from shared.domain.energy import BodyProfile
from shared.testing.fakes import InMemoryUnitOfWorkFactory

from nutrition.application.models import BodyComposition, UserProfile
from nutrition.application.ports import BodyMetricsRepository, MealRepository, ProfileRepository
from nutrition.domain.day import resolve_zone
from nutrition.domain.meal import CHAT_SOURCE, YAZIO_SOURCE, Meal

_ONE_US = timedelta(microseconds=1)
_LOCALES = {"ru", "en"}


class InMemoryMeals:
    def __init__(self) -> None:
        self.rows: dict[UUID, list[Meal]] = {}

    async def add(self, user_id: UUID, meal: Meal) -> Meal:
        meal = meal.with_recorded_at(meal.recorded_at.astimezone(UTC))
        rows = self.rows.setdefault(user_id, [])
        taken = {(m.source, m.recorded_at) for m in rows}
        while (meal.source, meal.recorded_at) in taken:
            meal = meal.with_recorded_at(meal.recorded_at + _ONE_US)
        rows.append(meal)
        return meal

    async def between(self, user_id: UUID, start: datetime, end: datetime) -> list[Meal]:
        found = [
            m
            for m in self.rows.get(user_id, [])
            if start <= m.recorded_at < end and m.source in (CHAT_SOURCE, YAZIO_SOURCE)
        ]
        return sorted(found, key=lambda m: m.recorded_at)

    async def recent(self, user_id: UUID, limit: int) -> list[Meal]:
        return sorted(self.rows.get(user_id, []), key=lambda m: m.recorded_at, reverse=True)[:limit]


class InMemoryProfiles:
    def __init__(self) -> None:
        self.rows: dict[UUID, tuple[str | None, dict[str, Any]]] = {}

    def seed(
        self,
        user_id: UUID,
        *,
        timezone: str | None = "UTC",
        preferences: dict[str, Any] | None = None,
    ) -> None:
        self.rows[user_id] = (timezone, dict(preferences or {}))

    async def get(self, user_id: UUID) -> UserProfile:
        if user_id not in self.rows:
            return UserProfile.default()
        timezone, prefs = self.rows[user_id]
        locale = prefs.get("locale")
        body = prefs.get("body_profile")
        return UserProfile(
            timezone=resolve_zone(timezone),
            locale=locale if isinstance(locale, str) and locale in _LOCALES else None,
            body=BodyProfile.from_mapping(body if isinstance(body, Mapping) else {}),
        )

    async def update_body_profile(
        self, user_id: UUID, changes: Mapping[str, object]
    ) -> BodyProfile:
        timezone, prefs = self.rows.get(user_id, ("UTC", {}))
        raw_body = prefs.get("body_profile")
        body = dict(raw_body) if isinstance(raw_body, Mapping) else {}
        for key, value in changes.items():
            if value is None:
                body.pop(key, None)
            else:
                body[key] = value
        prefs["body_profile"] = body
        self.rows[user_id] = (timezone, prefs)
        return BodyProfile.from_mapping(body)


class InMemoryBodyMetrics:
    def __init__(self) -> None:
        self.rows: dict[UUID, list[BodyComposition]] = {}

    def seed(self, user_id: UUID, composition: BodyComposition) -> None:
        self.rows.setdefault(user_id, []).append(composition)

    async def latest(self, user_id: UUID) -> BodyComposition | None:
        rows = self.rows.get(user_id, [])
        return max(rows, key=lambda c: c.recorded_at.astimezone(UTC)) if rows else None


class FakeSync:
    def __init__(self) -> None:
        self.calls = 0

    async def refresh(self) -> None:
        self.calls += 1


def in_memory_uow(
    meals: InMemoryMeals, profiles: InMemoryProfiles, metrics: InMemoryBodyMetrics
) -> InMemoryUnitOfWorkFactory:
    return InMemoryUnitOfWorkFactory(
        {MealRepository: meals, ProfileRepository: profiles, BodyMetricsRepository: metrics}
    )
