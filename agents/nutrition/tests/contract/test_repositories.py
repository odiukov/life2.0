"""One behavior contract for every MealRepository/ProfileRepository/BodyMetricsRepository backend."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from nutrition.adapters.db import nutrition_uow
from nutrition.application.models import BodyComposition
from nutrition.application.ports import BodyMetricsRepository, MealRepository, ProfileRepository
from nutrition.domain.meal import CHAT_SOURCE, YAZIO_SOURCE, Macros, Meal, MealItem, MealType
from nutrition.testing import InMemoryBodyMetrics, InMemoryMeals, InMemoryProfiles, in_memory_uow
from shared.adapters.db.engine import create_engine
from shared.config import DatabaseSettings
from shared.domain.energy import ActivityLevel, BodyProfile, Sex
from shared.ports.uow import UnitOfWorkFactory
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

T0 = datetime(2026, 10, 13, 12, 0, tzinfo=UTC)


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    seed_user: Callable[..., Awaitable[None]]
    seed_body: Callable[[UUID, BodyComposition], Awaitable[None]]


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    meals, profiles, metrics = InMemoryMeals(), InMemoryProfiles(), InMemoryBodyMetrics()

    async def seed_user(
        user_id: UUID, timezone: str | None = "UTC", preferences: dict[str, Any] | None = None
    ) -> None:
        profiles.seed(user_id, timezone=timezone, preferences=preferences)

    async def seed_body(user_id: UUID, composition: BodyComposition) -> None:
        metrics.seed(user_id, composition)

    yield Backend(in_memory_uow(meals, profiles, metrics), seed_user, seed_body)


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))
    admin = create_async_engine(urls.admin)

    async def seed_user(
        user_id: UUID, timezone: str | None = "UTC", preferences: dict[str, Any] | None = None
    ) -> None:
        # The real schema is NOT NULL: None seeds the empty-string fallback case.
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, name, timezone, preferences) "
                    "VALUES (:id, 'u', :tz, CAST(:prefs AS jsonb))"
                ),
                {"id": user_id, "tz": timezone or "", "prefs": json.dumps(preferences or {})},
            )

    async def seed_body(user_id: UUID, composition: BodyComposition) -> None:
        data = {
            "weight_kg": composition.weight_kg,
            "body_fat_pct": composition.body_fat_pct,
            "bmr_kcal": composition.bmr_kcal,
        }
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) "
                    "VALUES (:uid, 'body', 'body_composition', 'apple_health', :at, CAST(:data AS jsonb))"
                ),
                {"uid": user_id, "at": composition.recorded_at, "data": json.dumps(data)},
            )

    try:
        yield Backend(nutrition_uow(engine), seed_user, seed_body)
    finally:
        await engine.dispose()
        await admin.dispose()


BACKENDS: dict[str, Callable[[pytest.FixtureRequest], AsyncIterator[Backend]]] = {
    "memory": memory_backend,
    "sql": sql_backend,
}


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = BACKENDS[request.param](request)
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


def meal(at: datetime, kcal: float = 100, source: str = CHAT_SOURCE) -> Meal:
    return Meal.from_items(
        recorded_at=at,
        items=(MealItem("суп", 250, Macros(kcal=kcal, protein_g=5, carbs_g=10, fat_g=3)),),
        meal_type=MealType.LUNCH,
        source=source,
    )


async def test_between_is_half_open_ascending_and_includes_yazio(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    async with backend.uow.for_user(uid) as uow:
        repo = uow.repo(MealRepository)
        await repo.add(uid, meal(T0 + timedelta(hours=2)))
        await repo.add(uid, meal(T0, source=YAZIO_SOURCE))
        await repo.add(uid, meal(T0 + timedelta(days=1)))
    async with backend.uow.for_user(uid) as uow:
        found = await uow.repo(MealRepository).between(uid, T0, T0 + timedelta(days=1))
    assert [m.recorded_at for m in found] == [T0, T0 + timedelta(hours=2)]
    assert found[0].source == YAZIO_SOURCE
    assert found[1].items[0].name == "суп"
    assert found[1].totals.kcal == 100


async def test_same_timestamp_is_shifted_not_rejected(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    async with backend.uow.for_user(uid) as uow:
        first = await uow.repo(MealRepository).add(uid, meal(T0, kcal=100))
        second = await uow.repo(MealRepository).add(uid, meal(T0, kcal=50))
    assert first.recorded_at == T0
    assert second.recorded_at == T0 + timedelta(microseconds=1)
    async with backend.uow.for_user(uid) as uow:
        found = await uow.repo(MealRepository).between(uid, T0, T0 + timedelta(minutes=1))
    assert sum(m.totals.kcal for m in found) == 150


async def test_recent_is_newest_first_and_limited(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    async with backend.uow.for_user(uid) as uow:
        for hours in range(5):
            await uow.repo(MealRepository).add(uid, meal(T0 + timedelta(hours=hours)))
    async with backend.uow.for_user(uid) as uow:
        found = await uow.repo(MealRepository).recent(uid, 3)
    assert [m.recorded_at for m in found] == [T0 + timedelta(hours=h) for h in (4, 3, 2)]


async def test_users_do_not_see_each_other(backend: Backend) -> None:
    a, b = uuid4(), uuid4()
    await backend.seed_user(a)
    await backend.seed_user(b)
    async with backend.uow.for_user(a) as uow:
        await uow.repo(MealRepository).add(a, meal(T0))
    async with backend.uow.for_user(b) as uow:
        assert await uow.repo(MealRepository).recent(b, 10) == []


@pytest.mark.parametrize("zone", [None, "", "Mars/Olympus"])
async def test_profile_zone_falls_back_to_utc(backend: Backend, zone: str | None) -> None:
    uid = uuid4()
    await backend.seed_user(uid, timezone=zone)
    async with backend.uow.for_user(uid) as uow:
        profile = await uow.repo(ProfileRepository).get(uid)
    assert profile.timezone == ZoneInfo("UTC")


async def test_profile_reads_locale_and_body(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(
        uid,
        timezone="Europe/Lisbon",
        preferences={"locale": "en", "body_profile": {"height_cm": 180, "activity_level": "light"}},
    )
    async with backend.uow.for_user(uid) as uow:
        profile = await uow.repo(ProfileRepository).get(uid)
    assert profile.timezone == ZoneInfo("Europe/Lisbon")
    assert profile.locale == "en"
    assert profile.body == BodyProfile(height_cm=180, activity_level=ActivityLevel.LIGHT)


async def test_body_profile_merge_and_clear(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid, preferences={"body_profile": {"age": 30, "height_cm": 180}})
    async with backend.uow.for_user(uid) as uow:
        merged = await uow.repo(ProfileRepository).update_body_profile(
            uid, {"age": 31, "height_cm": None}
        )
    assert merged == BodyProfile(age=31)
    async with backend.uow.for_user(uid) as uow:
        assert (await uow.repo(ProfileRepository).get(uid)).body == BodyProfile(age=31)


async def test_latest_body_composition(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    async with backend.uow.for_user(uid) as uow:
        assert await uow.repo(BodyMetricsRepository).latest(uid) is None
    await backend.seed_body(uid, BodyComposition(T0 + timedelta(days=1), 79.5, 19.5, 1690.0))
    await backend.seed_body(uid, BodyComposition(T0, 80.0, 20.0, 1700.0))
    async with backend.uow.for_user(uid) as uow:
        latest = await uow.repo(BodyMetricsRepository).latest(uid)
    assert latest is not None
    assert latest.weight_kg == 79.5
    assert latest.bmr_kcal == 1690.0


async def test_between_excludes_other_sources_and_rows_before_start(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    async with backend.uow.for_user(uid) as uow:
        repo = uow.repo(MealRepository)
        await repo.add(uid, meal(T0 - timedelta(microseconds=1)))
        await repo.add(uid, meal(T0, source="other"))
        await repo.add(uid, meal(T0, source=CHAT_SOURCE))
        await repo.add(uid, meal(T0, source=YAZIO_SOURCE))
    async with backend.uow.for_user(uid) as uow:
        found = await uow.repo(MealRepository).between(uid, T0, T0 + timedelta(hours=1))
    assert {m.source for m in found} == {CHAT_SOURCE, YAZIO_SOURCE}
    assert len(found) == 2
    assert all(m.recorded_at == T0 for m in found)


async def test_collision_shifts_until_the_first_free_instant(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    async with backend.uow.for_user(uid) as uow:
        repo = uow.repo(MealRepository)
        await repo.add(uid, meal(T0))
        await repo.add(uid, meal(T0 + timedelta(microseconds=1)))
        third = await repo.add(uid, meal(T0))
    assert third.recorded_at == T0 + timedelta(microseconds=2)


async def test_unknown_profile_is_default_and_locale_validation_is_safe(backend: Backend) -> None:
    uid = uuid4()
    async with backend.uow.for_user(uid) as uow:
        profile = await uow.repo(ProfileRepository).get(uid)
    assert profile.timezone == ZoneInfo("UTC")
    assert profile.locale is None
    assert profile.body == BodyProfile()
    await backend.seed_user(
        uid, preferences={"locale": {"unexpected": "en"}, "body_profile": "invalid"}
    )
    async with backend.uow.for_user(uid) as uow:
        profile = await uow.repo(ProfileRepository).get(uid)
    assert profile.locale is None
    assert profile.body == BodyProfile()


async def test_profile_merge_clear_and_other_preferences_are_isolated(backend: Backend) -> None:
    a, b = uuid4(), uuid4()
    for uid in (a, b):
        await backend.seed_user(
            uid,
            timezone="Europe/Lisbon",
            preferences={"locale": "en", "body_profile": {"age": 30, "height_cm": 180}},
        )
    async with backend.uow.for_user(a) as uow:
        merged = await uow.repo(ProfileRepository).update_body_profile(
            a, {"age": None, "sex": "female"}
        )
    assert merged == BodyProfile(height_cm=180, sex=Sex.FEMALE)
    async with backend.uow.for_user(a) as uow:
        profile = await uow.repo(ProfileRepository).get(a)
    assert profile.timezone == ZoneInfo("Europe/Lisbon")
    assert profile.locale == "en"
    async with backend.uow.for_user(b) as uow:
        assert (await uow.repo(ProfileRepository).get(b)).body.age == 30


async def test_metrics_are_isolated_between_users(backend: Backend) -> None:
    a, b = uuid4(), uuid4()
    await backend.seed_user(a)
    await backend.seed_user(b)
    await backend.seed_body(a, BodyComposition(T0, 80, 20, 1700))
    async with backend.uow.for_user(b) as uow:
        assert await uow.repo(BodyMetricsRepository).latest(b) is None


async def test_equivalent_instants_collide_and_dst_fold_instants_remain_distinct(
    backend: Backend,
) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    zone = ZoneInfo("Europe/Lisbon")
    first_at = datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=0)
    second_at = datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=1)
    async with backend.uow.for_user(uid) as uow:
        repo = uow.repo(MealRepository)
        first = await repo.add(uid, meal(first_at))
        duplicate = await repo.add(uid, meal(first_at.astimezone(UTC)))
        second = await repo.add(uid, meal(second_at))
    assert first.recorded_at.astimezone(UTC) == first_at.astimezone(UTC)
    assert duplicate.recorded_at.astimezone(UTC) == first_at.astimezone(UTC) + timedelta(
        microseconds=1
    )
    assert second.recorded_at.astimezone(UTC) == second_at.astimezone(UTC)
    async with backend.uow.for_user(uid) as uow:
        found = await uow.repo(MealRepository).between(
            uid, first_at, (second_at.astimezone(UTC) + timedelta(minutes=1)).astimezone(zone)
        )
    assert len(found) == 3
    assert [m.recorded_at.astimezone(UTC) for m in found] == sorted(
        m.recorded_at.astimezone(UTC) for m in found
    )


async def test_latest_body_composition_compares_instants_during_dst_fold(backend: Backend) -> None:
    uid = uuid4()
    await backend.seed_user(uid)
    zone = ZoneInfo("Europe/Lisbon")
    earlier = datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=0)
    later = datetime(2026, 10, 25, 1, 30, tzinfo=zone, fold=1)
    await backend.seed_body(uid, BodyComposition(earlier, 80, 20, 1700))
    await backend.seed_body(uid, BodyComposition(later, 79, 19, 1690))
    async with backend.uow.for_user(uid) as uow:
        latest = await uow.repo(BodyMetricsRepository).latest(uid)
    assert latest is not None
    assert latest.weight_kg == 79
    assert latest.recorded_at.astimezone(UTC) == later.astimezone(UTC)
