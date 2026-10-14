from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

import pytest
from medication.application.data import AdherenceData, window_days
from medication.application.ports import MedicationRepository
from medication.domain.medication import Medication, intake_data
from medication.testing import InMemoryMedications
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory

NOW = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)


async def test_window_counts_and_no_medication_answer() -> None:
    user, meds, logs = uuid4(), InMemoryMedications(), InMemoryHealthLogs()
    uow = InMemoryUnitOfWorkFactory({MedicationRepository: meds, HealthLogRepository: logs})
    data = AdherenceData(JsonTranslator.from_dir(find_locales_dir()), "ru")

    def req(params: dict[str, object]) -> SkillRequest:
        return SkillRequest(
            task_id="t",
            context_id="c",
            text="как с приёмом?",
            user_id=user,
            skill_id="analyze_adherence",
            for_date=None,
            is_peer_call=False,
            params=params,
        )

    async with uow.for_user(user) as tx:
        none = await data.load(tx, req({}), UserSettings(ZoneInfo("UTC"), "ru"), NOW)
    assert none.answer == "Нет активных лекарств — анализировать нечего."
    async with uow.for_user(user) as tx:
        mid = await tx.repo(MedicationRepository).add(
            Medication(None, "vitamin-d", "2000 IU", "every morning", None, None)
        )
    med = Medication(mid, "vitamin-d", "2000 IU", "every morning", None, None)
    for days in (1, 2, 20):
        logs.seed(
            user,
            HealthLogRow(
                "medication_taken",
                NOW - timedelta(days=days),
                intake_data(med, "", None, None),
                "manual",
                "medication",
            ),
        )
    logs.seed(
        user,
        HealthLogRow(
            "medication_taken", NOW, intake_data(med, "", None, None), "manual", "nutrition"
        ),
    )
    async with uow.for_user(user) as tx:
        loaded = await data.load(
            tx, req({"window_days": "7"}), UserSettings(ZoneInfo("UTC"), "ru"), NOW
        )
    window, summary = loaded.sections
    assert window.body == "Last 7 days"
    assert (
        summary.body
        == "- vitamin-d | schedule: every morning | dose: 2000 IU | taken 2× | last: 2026-10-12 20:00"
    )


@pytest.mark.parametrize(
    ("raw", "expected"), [(None, 14), ("bad", 14), ("7", 7), (0, 1), (-10, 1), (1000, 90)]
)
def test_window_bounds(raw: object, expected: int) -> None:
    assert window_days(raw) == expected
