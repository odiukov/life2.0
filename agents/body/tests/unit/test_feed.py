from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from body.application.feed import collect
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


def scale(source: str, at: datetime, **data: object) -> HealthLogRow:
    return HealthLogRow("body_composition", at, data, source, "body")


async def test_weight_with_fat_and_duplicate_scale_rows() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    data = await run(
        scale("vihealth", at, weight_kg=78.4, body_fat_pct=18.2),
        scale("SourceProxy", at + timedelta(minutes=2), weight_kg=78.4),
    )
    assert [i["text"] for i in data["items"]] == ["Weight 78.4 kg · fat 18.2%"]


async def test_rows_without_weight_are_skipped() -> None:
    data = await run(scale("vihealth", datetime(2026, 10, 14, 5, 0, tzinfo=UTC), body_fat_pct=18.2))
    assert data["items"] == []


async def test_actual_skill_caps_collector_results_and_preserves_same_source_events() -> None:
    at = datetime(2026, 10, 13, 5, 0, tzinfo=UTC)
    rows = []
    for minute in range(60):
        at = at.replace(minute=minute)
        rows.append(scale("vihealth", at, weight_kg=78.4, body_fat_pct=18.2))
    data = await run(*rows, day=date(2026, 10, 13))
    assert len(data["items"]) == 50
    assert all(i["kind"] == "event" for i in data["items"])
    assert data["items"][0]["at"] == at.isoformat()


async def test_actual_skill_localizes_collector_events() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    data = await run(scale("vihealth", at, weight_kg=78.4, body_fat_pct=18.2), locale="ru")
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == ["Вес 78,4 кг · жир 18,2%"]


async def test_unrelated_agent_rows_are_ignored() -> None:
    at = datetime(2026, 10, 14, 5, 0, tzinfo=UTC)
    row = scale("vihealth", at, weight_kg=78.4, body_fat_pct=18.2)
    unrelated = HealthLogRow(row.type, row.recorded_at, row.data, row.source, "nutrition")
    assert (await run(unrelated))["items"] == []
