from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from mood.application.feed import collect
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


def entry(at: datetime, **data: object) -> HealthLogRow:
    return HealthLogRow("mood", at, data, "manual", "mood")


async def test_mood_entries_with_and_without_scores() -> None:
    morning, evening = (
        datetime(2026, 10, 14, 6, 0, tzinfo=UTC),
        datetime(2026, 10, 14, 17, 0, tzinfo=UTC),
    )
    data = await run(entry(morning, mood_score=7, energy=6), entry(evening, raw_text="tired"))
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == [
        "Mood noted",
        "Mood 7/10 · energy 6/10",
    ]


async def test_actual_skill_caps_collector_results_and_preserves_same_source_events() -> None:
    at = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    rows = []
    for minute in range(60):
        at = at.replace(minute=minute)
        rows.append(entry(at, mood_score=7, energy=6))
    data = await run(*rows, day=date(2026, 10, 13))
    assert len(data["items"]) == 50
    assert all(i["kind"] == "event" for i in data["items"])
    assert data["items"][0]["at"] == at.isoformat()


async def test_actual_skill_localizes_collector_events() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    data = await run(entry(at, mood_score=7, energy=6), locale="ru")
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == [
        "Настроение 7/10 · энергия 6/10"
    ]


async def test_unrelated_agent_rows_are_ignored() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    row = entry(at, mood_score=7, energy=6)
    unrelated = HealthLogRow(row.type, row.recorded_at, row.data, row.source, "nutrition")
    assert (await run(unrelated))["items"] == []


async def test_unrelated_history_does_not_create_an_insight() -> None:
    rows = [
        HealthLogRow("mood", NOW - timedelta(days=offset), {"mood_score": 7}, "manual", "nutrition")
        for offset in range(1, 7)
    ]
    assert (await run(*rows))["items"] == []
