from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.feed import FeedSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Feed
from shared.testing.fakes import (
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)
from shared.testing.feed_contract import assert_feed_contract
from workout.application.feed import collect

LOCALES = Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales"
TR = JsonTranslator.from_dir(LOCALES)
KYIV = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
DAY = date(2026, 10, 14)
USER = uuid4()


async def run(*rows: HealthLogRow, day: date = DAY, locale: str = "en") -> dict:  # type: ignore[type-arg]
    logs, settings = InMemoryHealthLogs(), InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv", locale=locale)
    for row in rows:
        logs.seed(USER, row)
    skill = FeedSkill(
        uow=InMemoryUnitOfWorkFactory(
            {HealthLogRepository: logs, UserSettingsRepository: settings}
        ),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(
        SkillRequest("t", "c", "", USER, Feed.EVENTS, None, False, {"date": day.isoformat()}), ()
    )
    assert_feed_contract(result.data, day, KYIV)
    return result.data  # type: ignore[return-value]


def activity(source: str, at: datetime, **data: object) -> HealthLogRow:
    return HealthLogRow(
        "activity",
        at,
        {"activity_type": "running", "name": "Evening run", **data},
        source,
        "workout",
    )


async def test_a_workout_reads_name_duration_and_distance() -> None:
    at = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    data = await run(activity("garmin", at, duration_seconds=3600, distance_meters=10200))
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == [
        "Evening run · 1 h 0 min · 10.2 km"
    ]


async def test_duplicate_workout_within_ten_minutes_is_one_item() -> None:
    at = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    data = await run(
        activity("SourceProxy", at + timedelta(minutes=4), duration_seconds=3500),
        activity("garmin", at, duration_seconds=3600),
    )
    events = [i for i in data["items"] if i["kind"] == "event"]
    assert len(events) == 1
    assert ":garmin:" in events[0]["id"]


async def test_unnamed_workout_without_duration() -> None:
    at = datetime(2026, 10, 14, 15, 0, tzinfo=UTC)
    data = await run(HealthLogRow("activity", at, {"activity_type": "unknown"}, "chat", "workout"))
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == ["Workout"]


async def test_actual_skill_caps_collector_results_and_preserves_same_source_events() -> None:
    at = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    rows = []
    for minute in range(60):
        at = at.replace(minute=minute)
        rows.append(activity("garmin", at, duration_seconds=3600))
    data = await run(*rows, day=date(2026, 10, 13))
    assert len(data["items"]) == 50
    assert all(i["kind"] == "event" for i in data["items"])
    assert data["items"][0]["at"] == at.isoformat()


async def test_actual_skill_localizes_collector_events() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    data = await run(activity("garmin", at, duration_seconds=3600), locale="ru")
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == ["Evening run · 1 ч 0 мин"]


async def test_unrelated_agent_rows_are_ignored() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    row = activity("garmin", at, duration_seconds=3600)
    unrelated = HealthLogRow(row.type, row.recorded_at, row.data, row.source, "nutrition")
    assert (await run(unrelated))["items"] == []


async def test_long_workout_name_is_clipped_by_actual_skill() -> None:
    data = await run(activity("chat", datetime(2026, 10, 14, 5, 0, tzinfo=UTC), name="a" * 200))
    assert len(data["items"][0]["text"]) == 140
    assert data["items"][0]["text"].endswith("…")
