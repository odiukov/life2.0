from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from recovery.application.feed import collect
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.feed import FeedSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Feed
from shared.testing import dashboard_golden as g
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


async def run(*rows: HealthLogRow, day: date = DAY, locale: str = "en", meals_input=()) -> dict:
    logs, settings = InMemoryHealthLogs(), InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv", locale=locale)
    for row in rows:
        logs.seed(USER, row)
    repos = {HealthLogRepository: logs, UserSettingsRepository: settings}
    skill = FeedSkill(
        uow=InMemoryUnitOfWorkFactory(repos),
        clock=FixedClock(NOW),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(
        SkillRequest("t", "c", "", USER, Feed.EVENTS, None, False, {"date": day.isoformat()}), ()
    )
    assert not result.failed
    assert_feed_contract(result.data, day, KYIV)
    return result.data


async def test_recovery_has_only_todays_insight() -> None:
    data = await run(*g.health_log_rows(), day=DAY)
    assert len(data["items"]) == 1
    assert all(i["kind"] == "insight" for i in data["items"])
    past = await run(day=date(2026, 10, 13))
    assert past["items"] == []


async def test_russian_nonempty_insight_and_source_isolation() -> None:
    rows = g.health_log_rows()
    data = await run(*rows, locale="ru")
    assert [i["text"] for i in data["items"]] == [
        "Показатели восстановления близки к обычным. Умеренная тренировка допустима."
    ]
    unrelated = [HealthLogRow(r.type, r.recorded_at, r.data, r.source, "nutrition") for r in rows]
    assert (await run(*unrelated))["items"] == []


async def test_healthkit_daily_stats_are_included_with_owner_filter() -> None:
    from recovery.application.dashboard import daily_metrics
    from shared.dashboard import DashboardContext
    from shared.ports.users import UserSettings

    logs = InMemoryHealthLogs()
    logs.seed(
        USER,
        HealthLogRow(
            "daily_stats", NOW, {"stress_avg": 25, "resting_hr": 55}, "healthkit", "system"
        ),
    )
    logs.seed(
        USER,
        HealthLogRow(
            "daily_stats", NOW + timedelta(minutes=1), {"stress_avg": 99}, "foreign", "nutrition"
        ),
    )
    factory = InMemoryUnitOfWorkFactory({HealthLogRepository: logs})
    async with factory.for_user(USER) as tx:
        metrics = await daily_metrics(tx, DashboardContext(USER, UserSettings(KYIV, "en"), NOW), 9)
    assert metrics[DAY]["stress"] == 25
    assert metrics[DAY]["rhr"] == 55
