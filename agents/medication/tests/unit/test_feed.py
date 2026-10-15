from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo

from medication.application.feed import collect
from medication.application.ports import MedicationRepository
from medication.domain.medication import Medication
from medication.testing import InMemoryMedications
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


async def run(*rows: HealthLogRow, day: date = DAY, locale: str = "en", medications=()) -> dict:
    logs, settings = InMemoryHealthLogs(), InMemoryUserSettings()
    settings.seed(USER, timezone="Europe/Kyiv", locale=locale)
    for row in rows:
        logs.seed(USER, row)
    meds = InMemoryMedications()
    for med in medications:
        await meds.add(med)
    repos = {
        HealthLogRepository: logs,
        UserSettingsRepository: settings,
        MedicationRepository: meds,
    }
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


async def test_intakes_with_and_without_dose() -> None:
    a, b = datetime(2026, 10, 14, 5, 15, tzinfo=UTC), datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
    data = await run(
        HealthLogRow(
            "medication_taken",
            a,
            {"name": "Vitamin D", "dose_at_time": "2000 IU"},
            "chat",
            "medication",
        ),
        HealthLogRow(
            "medication_taken", b, {"name": "Magnesium", "dose_at_time": None}, "chat", "medication"
        ),
    )
    assert [i["text"] for i in data["items"] if i["kind"] == "event"] == [
        "Took Magnesium",
        "Took Vitamin D · 2000 IU",
    ]


async def test_actual_skill_cap_localization_and_agent_isolation() -> None:
    rows = [
        HealthLogRow(
            "medication_taken",
            NOW.replace(minute=n),
            {"name": "x", "completed": True},
            "chat",
            "medication",
        )
        for n in range(60)
    ]
    data = await run(*rows, locale="ru")
    assert len(data["items"]) == 50
    assert all(i["text"].startswith("Принято: x") for i in data["items"] if i["kind"] == "event")
    other = HealthLogRow("medication_taken", NOW, {"name": "wrong"}, "chat", "nutrition")
    assert not [i for i in (await run(other))["items"] if i["kind"] == "event"]


async def test_russian_nonempty_insight() -> None:
    rows = [
        HealthLogRow(
            "medication_taken", NOW - timedelta(days=n), {"name": "x"}, "chat", "medication"
        )
        for n in range(7)
    ]
    data = await run(*rows, locale="ru")
    assert [i["text"] for i in data["items"] if i["kind"] == "insight"] == [
        "Все приёмы за неделю отмечены. Так держать."
    ]


async def test_empty_user_has_no_adherence_insight() -> None:
    assert (await run())["items"] == []


async def test_active_schedule_keeps_insight_without_intakes() -> None:
    med = Medication(None, "Vitamin D", None, "daily", None, None)
    items = (await run(medications=[med]))["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "insight"
    assert "Vitamin D" in items[0]["text"]


async def test_historical_intake_keeps_insight_without_active_schedule() -> None:
    row = HealthLogRow(
        "medication_taken", NOW - timedelta(days=10), {"name": "retired"}, "chat", "medication"
    )
    items = (await run(row))["items"]
    assert len(items) == 1
    assert items[0]["kind"] == "insight"
