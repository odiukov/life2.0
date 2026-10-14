"""One behavior contract for UserSettingsRepository and HealthLogRepository backends."""

import json
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.db.health_logs import SqlHealthLogs
from shared.adapters.db.uow import SqlUnitOfWorkFactory
from shared.adapters.db.users import SqlUserSettings
from shared.config import DatabaseSettings
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.uow import UnitOfWorkFactory
from shared.ports.users import UserSettings, UserSettingsRepository
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory, InMemoryUserSettings
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

T0 = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)


@dataclass
class Backend:
    uow: UnitOfWorkFactory
    seed_user: Callable[[UUID, str | None, dict[str, Any]], Awaitable[None]]


async def memory_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    users, logs = InMemoryUserSettings(), InMemoryHealthLogs()

    async def seed(user: UUID, tz: str | None, prefs: dict[str, Any]) -> None:
        users.seed(user, timezone=tz, locale=prefs.get("locale"))

    yield Backend(
        InMemoryUnitOfWorkFactory({UserSettingsRepository: users, HealthLogRepository: logs}), seed
    )


async def sql_backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    urls: PostgresUrls = request.getfixturevalue("clean_db")
    admin = create_async_engine(urls.admin)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": urls.rw}))

    async def seed(user: UUID, tz: str | None, prefs: dict[str, Any]) -> None:
        async with admin.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO users (id, name, timezone, preferences) VALUES (:id, 'u', :tz, CAST(:p AS jsonb))"
                ),
                {"id": user, "tz": tz or "", "p": json.dumps(prefs)},
            )

    try:
        yield Backend(
            SqlUnitOfWorkFactory(
                engine,
                {UserSettingsRepository: SqlUserSettings, HealthLogRepository: SqlHealthLogs},
            ),
            seed,
        )
    finally:
        await engine.dispose()
        await admin.dispose()


BACKENDS = {"memory": memory_backend, "sql": sql_backend}


@pytest.fixture(params=["memory", pytest.param("sql", marks=pytest.mark.integration)])
async def backend(request: pytest.FixtureRequest) -> AsyncIterator[Backend]:
    generator = BACKENDS[request.param](request)
    try:
        yield await generator.__anext__()
    finally:
        await generator.aclose()


@pytest.mark.parametrize(
    ("tz", "prefs", "expected"),
    [
        ("Europe/Lisbon", {"locale": "ru"}, UserSettings(ZoneInfo("Europe/Lisbon"), "ru")),
        ("Not/AZone", {"locale": "de"}, UserSettings(ZoneInfo("UTC"), None)),
        (None, {}, UserSettings(ZoneInfo("UTC"), None)),
    ],
)
async def test_user_settings_resolve_zone_and_locale(backend: Backend, tz, prefs, expected) -> None:  # type: ignore[no-untyped-def]
    user = uuid4()
    await backend.seed_user(user, tz, prefs)
    async with backend.uow.for_user(user) as uow:
        assert await uow.repo(UserSettingsRepository).get(user) == expected


async def test_unknown_user_gets_defaults(backend: Backend) -> None:
    user = uuid4()
    async with backend.uow.for_user(user) as uow:
        assert await uow.repo(UserSettingsRepository).get(user) == UserSettings(
            ZoneInfo("UTC"), None
        )


def test_today_is_the_local_date() -> None:
    settings = UserSettings(ZoneInfo("Europe/Moscow"), None)
    assert settings.today(datetime(2026, 10, 13, 22, 30, tzinfo=UTC)) == date(2026, 10, 14)


def row(
    type_: str, at: datetime, source: str = "chat", agent: str = "sleep", **data: object
) -> HealthLogRow:
    return HealthLogRow(type=type_, recorded_at=at, data=data, source=source, agent=agent)


async def test_health_logs_filters_orders_and_limits(backend: Backend) -> None:
    user = uuid4()
    await backend.seed_user(user, "UTC", {})
    async with backend.uow.for_user(user) as uow:
        repo = uow.repo(HealthLogRepository)
        await repo.add(user, row("sleep_session", T0, duration_seconds=25200))
        await repo.add(user, row("sleep_session", T0 + timedelta(days=1), source="garmin"))
        await repo.add(
            user, row("daily_stats", T0 - timedelta(hours=1), agent="system", resting_hr=55)
        )
        await repo.add(user, row("habit", T0, agent="habits", habit_id="h1"))
        await repo.add(user, row("habit", T0 + timedelta(hours=1), agent="habits", habit_id="h2"))
        sessions = await repo.recent(user, types=["sleep_session"])
        assert [r.source for r in sessions] == ["garmin", "chat"]
        assert sessions[1].data == {"duration_seconds": 25200}
        limited = await repo.recent(user, types=["sleep_session", "daily_stats"], limit=2)
        assert [r.type for r in limited] == ["sleep_session", "sleep_session"]
        recent = await repo.recent(user, types=["sleep_session"], since=T0 + timedelta(hours=1))
        assert [r.source for r in recent] == ["garmin"]
        only_h1 = await repo.recent(user, types=["habit"], data_equals={"habit_id": "h1"})
        assert [r.data["habit_id"] for r in only_h1] == ["h1"]
        assert await repo.recent(user, types=["sleep_session"], agent="workout") == []


async def test_add_shifts_on_conflict_and_returns_the_stored_time(backend: Backend) -> None:
    user = uuid4()
    await backend.seed_user(user, "UTC", {})
    async with backend.uow.for_user(user) as uow:
        repo = uow.repo(HealthLogRepository)
        first = await repo.add(user, row("mood", T0, agent="mood", mood_score=6))
        second = await repo.add(user, row("mood", T0, agent="mood", mood_score=7))
        assert first == T0
        assert second == T0 + timedelta(microseconds=1)
        assert len(await repo.recent(user, types=["mood"])) == 2


async def test_rows_are_isolated_per_user(backend: Backend) -> None:
    a, b = uuid4(), uuid4()
    await backend.seed_user(a, "UTC", {})
    await backend.seed_user(b, "UTC", {})
    async with backend.uow.for_user(a) as uow:
        await uow.repo(HealthLogRepository).add(a, row("mood", T0, agent="mood"))
    async with backend.uow.for_user(b) as uow:
        assert await uow.repo(HealthLogRepository).recent(b, types=["mood"]) == []
