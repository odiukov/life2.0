from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from medication.application.attention import collect
from medication.application.ports import MedicationRepository
from medication.domain.attention import missed_today
from medication.domain.medication import Medication
from medication.testing import InMemoryMedications
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.attention import AttentionSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention
from shared.testing.attention_contract import assert_attention_contract
from shared.testing.fakes import (
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

TR = JsonTranslator.from_dir(Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales")
TODAY = date(2026, 10, 16)
EVENING = datetime(2026, 10, 16, 18, 30, tzinfo=UTC)  # 21:30 in Kyiv
NOON = datetime(2026, 10, 16, 9, 0, tzinfo=UTC)
USER = uuid4()
MED = Medication(uuid4(), "Vitamin D", None, "daily", None, None)


def test_missed_today_rule() -> None:
    days = {TODAY - timedelta(days=n) for n in range(1, 6)}
    assert missed_today(days, TODAY)
    assert not missed_today(days | {TODAY}, TODAY)
    assert not missed_today({TODAY - timedelta(days=n) for n in range(1, 5)}, TODAY)


def intake(days_ago: int, now: datetime = EVENING) -> HealthLogRow:
    at = now.replace(hour=6) - timedelta(days=days_ago)
    data = {"name": MED.name, "medication_id": str(MED.id)}
    return HealthLogRow("medication_taken", at, data, "chat", "medication")


async def run(*rows: HealthLogRow, now: datetime = EVENING) -> list[dict]:  # type: ignore[type-arg]
    logs, settings, meds = InMemoryHealthLogs(), InMemoryUserSettings(), InMemoryMedications()
    settings.seed(USER, timezone="Europe/Kyiv")
    assert MED.id is not None
    meds.rows[MED.id] = MED
    for row in rows:
        logs.seed(USER, row)
    skill = AttentionSkill(
        uow=InMemoryUnitOfWorkFactory(
            {
                HealthLogRepository: logs,
                UserSettingsRepository: settings,
                MedicationRepository: meds,
            }
        ),
        clock=FixedClock(now),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(SkillRequest("t", "c", "", USER, Attention.ITEMS, None, False, {}), ())
    assert_attention_contract(result.data)
    return result.data["items"]  # type: ignore[index, return-value]


async def test_evening_without_todays_intake() -> None:
    [item] = await run(*(intake(n) for n in range(1, 7)))
    assert item["id"] == f"medication:missed:{MED.id}:2026-10-16"
    assert (item["level"], item["text"]) == ("high", "Did you take Vitamin D?")
    assert item["action"] == {"type": "task", "prompt": "I took Vitamin D"}


async def test_not_before_evening_and_not_when_taken() -> None:
    assert await run(*(intake(n, NOON) for n in range(1, 7)), now=NOON) == []
    assert await run(*(intake(n) for n in range(0, 7))) == []
