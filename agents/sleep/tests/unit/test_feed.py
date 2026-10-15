from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
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
from sleep.application.feed import collect

LOCALES = Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales"
TR = JsonTranslator.from_dir(LOCALES)
KYIV = ZoneInfo("Europe/Kyiv")
NOW = datetime(2026, 10, 14, 9, 0, tzinfo=UTC)
DAY = date(2026, 10, 14)
USER = uuid4()


def night(
    source: str, end: datetime, duration_s: int = 27600, deep_s: int | None = 6600
) -> HealthLogRow:
    data: dict[str, object] = {
        "duration_seconds": duration_s,
        "end_time": end.isoformat(),
        "start_time": (end - timedelta(seconds=duration_s)).isoformat(),
    }
    if deep_s is not None:
        data["deep_sleep_seconds"] = deep_s
    return HealthLogRow("sleep_session", end, data, source, "sleep")


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


async def test_a_night_becomes_one_event_at_wake_time() -> None:
    wake = datetime(2026, 10, 14, 4, 40, tzinfo=UTC)  # 07:40 Kyiv
    data = await run(night("garmin", wake))
    events = [i for i in data["items"] if i["kind"] == "event"]
    assert events == [
        {
            "id": f"sleep:sleep_session:garmin:{wake.isoformat()}",
            "at": wake.isoformat(),
            "kind": "event",
            "text": "Slept 7 h 40 min · deep 1 h 50 min",
        }
    ]


async def test_same_night_from_two_sources_is_one_item() -> None:
    wake = datetime(2026, 10, 14, 4, 40, tzinfo=UTC)
    data = await run(night("SourceProxy", wake + timedelta(minutes=12)), night("garmin", wake))
    events = [i for i in data["items"] if i["kind"] == "event"]
    assert len(events) == 1
    assert ":garmin:" in events[0]["id"]


async def test_a_nap_hours_later_is_its_own_item() -> None:
    wake = datetime(2026, 10, 14, 4, 40, tzinfo=UTC)
    data = await run(
        night("garmin", wake),
        night("SourceProxy", wake + timedelta(hours=8), duration_s=1800, deep_s=None),
    )
    events = [i for i in data["items"] if i["kind"] == "event"]
    assert [e["text"] for e in events] == ["Slept 30 min", "Slept 7 h 40 min · deep 1 h 50 min"]


async def test_past_day_has_no_insight_and_other_days_are_ignored() -> None:
    yesterday_wake = datetime(2026, 10, 13, 4, 0, tzinfo=UTC)
    data = await run(
        night("garmin", yesterday_wake),
        night("garmin", datetime(2026, 10, 14, 4, 0, tzinfo=UTC)),
        day=date(2026, 10, 13),
    )
    assert [i["kind"] for i in data["items"]] == ["event"]


async def test_actual_skill_caps_collector_results_and_preserves_same_source_events() -> None:
    at = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    rows = []
    for minute in range(60):
        at = at.replace(minute=minute)
        rows.append(night("garmin", at))
    data = await run(*rows, day=date(2026, 10, 13))
    assert len(data["items"]) == 50
    assert all(i["kind"] == "event" for i in data["items"])
    assert data["items"][0]["at"] == at.isoformat()


async def test_actual_skill_localizes_collector_events() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    data = await run(night("garmin", at), locale="ru")
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == [
        "Сон 7 ч 40 мин · глубокий 1 ч 50 мин"
    ]


async def test_unrelated_agent_rows_are_ignored() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    row = night("garmin", at)
    unrelated = HealthLogRow(row.type, row.recorded_at, row.data, row.source, "nutrition")
    assert (await run(unrelated))["items"] == []


async def test_chat_end_outside_day_keeps_recorded_time_in_day() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    row = night("chat", at - timedelta(days=1))
    data = await run(HealthLogRow(row.type, at, row.data, row.source, row.agent))
    assert data["items"][0]["at"] == at.isoformat()


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        ([6, 8, 8], "Выше среднего за неделю в 2 из последних 3 ночей."),
        ([8, 8, 6], "Прошлой ночью сон короче среднего за неделю на 2,0 ч."),
    ],
)
async def test_russian_feed_localizes_nonempty_insights(hours: list[int], expected: str) -> None:
    rows = [
        night(
            "garmin", NOW - timedelta(days=2 - index, hours=1), duration_s=value * 3600, deep_s=None
        )
        for index, value in enumerate(hours)
    ]
    data = await run(*rows, locale="ru")
    assert [item["text"] for item in data["items"]] == [expected, f"Сон {hours[-1]} ч 0 мин"]
