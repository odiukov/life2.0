"""c0006 moves legacy Garmin sleep and Yazio meal rows onto the keys the new mappers produce."""

import json
from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest
from alembic import command
from shared.schema.migrate import alembic_config, upgrade
from shared.testing.pytest_plugin import PostgresUrls, run_blocking
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

pytestmark = pytest.mark.integration
Key = tuple[str, str, datetime]


async def _execute(url: str, sql: str, params: dict[str, object]) -> None:
    engine = create_async_engine(url)
    try:
        async with engine.begin() as conn:
            await conn.execute(text(sql), params)
    finally:
        await engine.dispose()


async def _keys(url: str, user: UUID) -> list[Key]:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            rows = await conn.execute(
                text(
                    "SELECT source, type, recorded_at FROM health_logs WHERE user_id = :u ORDER BY source, type, recorded_at"
                ),
                {"u": user},
            )
            return [(r.source, r.type, r.recorded_at.astimezone(UTC)) for r in rows]
    finally:
        await engine.dispose()


async def _forced(url: str) -> bool:
    engine = create_async_engine(url)
    try:
        async with engine.connect() as conn:
            return bool(
                (
                    await conn.execute(
                        text(
                            "SELECT relforcerowsecurity FROM pg_class WHERE relname = 'health_logs'"
                        )
                    )
                ).scalar_one()
            )
    finally:
        await engine.dispose()


def add(
    url: str, user: UUID, source: str, type_: str, at: datetime, data: dict[str, object]
) -> None:
    run_blocking(
        _execute(
            url,
            "INSERT INTO health_logs (user_id, agent, type, source, recorded_at, data) "
            "VALUES (:u, 'x', :t, :s, :r, CAST(:d AS jsonb))",
            {"u": user, "t": type_, "s": source, "r": at, "d": json.dumps(data)},
        )
    )


def test_legacy_rows_are_rekeyed(clean_db: PostgresUrls) -> None:
    command.downgrade(alembic_config(clean_db.owner), "c0005_sync")  # c0006's downgrade is a no-op
    try:
        user, utc_user = uuid4(), uuid4()
        run_blocking(
            _execute(
                clean_db.admin,
                "INSERT INTO users (id, name, timezone) VALUES (:a, 'a', 'America/New_York'), (:b, 'b', 'UTC')",
                {"a": user, "b": utc_user},
            )
        )
        at = datetime(2026, 10, 12, 23, 0, tzinfo=UTC)
        # Legacy sleep: 23:00 New York wall time stored as 23:00 UTC.
        add(clean_db.admin, user, "garmin", "sleep_session", at, {"duration_seconds": 1})
        # Legacy Yazio: breakfast at 08:00 UTC and dinner at 18:00 UTC of 2026-10-13.
        add(
            clean_db.admin,
            user,
            "yazio",
            "meal",
            datetime(2026, 10, 13, 8, 0, tzinfo=UTC),
            {"meal_type": "breakfast", "date": "2026-10-13"},
        )
        add(
            clean_db.admin,
            user,
            "yazio",
            "meal",
            datetime(2026, 10, 13, 18, 0, tzinfo=UTC),
            {"meal_type": "dinner", "date": "2026-10-13"},
        )
        # Untouched: activities were always true UTC; chat rows are not synced; a UTC user's keys are already right.
        add(
            clean_db.admin, user, "garmin", "activity", datetime(2026, 10, 13, 6, 0, tzinfo=UTC), {}
        )
        add(clean_db.admin, user, "chat", "sleep_session", at, {})
        add(clean_db.admin, utc_user, "garmin", "sleep_session", at, {})
    finally:
        upgrade(clean_db.owner)  # back to head, running c0006

    assert run_blocking(_keys(clean_db.admin, user)) == [
        ("chat", "sleep_session", at),
        ("garmin", "activity", datetime(2026, 10, 13, 6, 0, tzinfo=UTC)),
        ("garmin", "sleep_session", datetime(2026, 10, 13, 3, 0, tzinfo=UTC)),
        ("yazio", "meal", datetime(2026, 10, 13, 12, 0, tzinfo=UTC)),
        ("yazio", "meal", datetime(2026, 10, 13, 22, 0, tzinfo=UTC)),
    ]
    assert run_blocking(_keys(clean_db.admin, utc_user)) == [("garmin", "sleep_session", at)]
    assert run_blocking(_forced(clean_db.admin)) is True


@pytest.mark.parametrize("zone", ["Not/A_Zone", ""])
def test_unknown_timezone_uses_utc(clean_db: PostgresUrls, zone: str) -> None:
    command.downgrade(alembic_config(clean_db.owner), "c0005_sync")
    user = uuid4()
    at = datetime(2026, 10, 12, 23, tzinfo=UTC)
    meal_at = datetime(2026, 10, 13, 8, tzinfo=UTC)
    try:
        run_blocking(
            _execute(
                clean_db.admin,
                "INSERT INTO users (id, name, timezone) VALUES (:u, 'a', :z)",
                {"u": user, "z": zone},
            )
        )
        add(clean_db.admin, user, "garmin", "sleep_session", at, {})
        add(
            clean_db.admin,
            user,
            "yazio",
            "meal",
            meal_at,
            {"meal_type": "breakfast", "date": "2026-10-13"},
        )
    finally:
        upgrade(clean_db.owner)
    assert run_blocking(_keys(clean_db.admin, user)) == [
        ("garmin", "sleep_session", at),
        ("yazio", "meal", meal_at),
    ]
    assert run_blocking(_forced(clean_db.admin)) is True


@pytest.mark.parametrize(
    ("zone", "wall", "expected"),
    [
        (
            "America/New_York",
            datetime(2026, 11, 1, 1, 30, tzinfo=UTC),
            datetime(2026, 11, 1, 5, 30, tzinfo=UTC),
        ),
        (
            "Europe/Lisbon",
            datetime(2026, 10, 25, 1, 30, tzinfo=UTC),
            datetime(2026, 10, 25, 0, 30, tzinfo=UTC),
        ),
        (
            "Australia/Lord_Howe",
            datetime(2026, 4, 5, 1, 45, tzinfo=UTC),
            datetime(2026, 4, 4, 14, 45, tzinfo=UTC),
        ),
    ],
)
def test_overlap_chooses_first_occurrence(
    clean_db: PostgresUrls, zone: str, wall: datetime, expected: datetime
) -> None:
    """Without historical offsets, migration and mapper use the same fold=0 default."""
    command.downgrade(alembic_config(clean_db.owner), "c0005_sync")
    user = uuid4()
    try:
        run_blocking(
            _execute(
                clean_db.admin,
                "INSERT INTO users (id, name, timezone) VALUES (:u, 'a', :z)",
                {"u": user, "z": zone},
            )
        )
        add(clean_db.admin, user, "garmin", "sleep_session", wall, {})
    finally:
        upgrade(clean_db.owner)
    assert run_blocking(_keys(clean_db.admin, user)) == [("garmin", "sleep_session", expected)]
    assert run_blocking(_forced(clean_db.admin)) is True
