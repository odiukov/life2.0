from datetime import UTC, datetime, timedelta
from uuid import UUID

from medication.application.data import AdherenceData
from medication.application.ports import MedicationRepository
from medication.composition import MEDICATION_SPEC
from medication.domain.medication import Medication, intake_data
from medication.testing import InMemoryMedications
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.analysis.skill import AnalysisSkill
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FakePeerClient,
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)

NOW = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
USER = UUID(int=13)


async def test_prompt_snapshot(snapshot) -> None:  # type: ignore[no-untyped-def]
    meds, logs, users = InMemoryMedications(), InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(USER, timezone="Europe/Lisbon")
    uow = InMemoryUnitOfWorkFactory(
        {MedicationRepository: meds, HealthLogRepository: logs, UserSettingsRepository: users}
    )
    async with uow.for_user(USER) as tx:
        mid = await tx.repo(MedicationRepository).add(
            Medication(None, "vitamin-d", "2000 IU", "every morning", None, None)
        )
    med = Medication(mid, "vitamin-d", "2000 IU", "every morning", None, None)
    for days in (1, 3, 4):
        logs.seed(
            USER,
            HealthLogRow(
                "medication_taken",
                NOW - timedelta(days=days),
                intake_data(med, "", None, None),
                "manual",
                "medication",
            ),
        )
    llm = FakeLLM()
    llm.queue_text("ok")
    tr = JsonTranslator.from_dir(find_locales_dir())
    handler = AnalysisSkill(
        spec=MEDICATION_SPEC,
        mode="analyze_adherence",
        data=AdherenceData(tr, "ru"),
        llm=llm,
        uow=uow,
        peers=FakePeerClient({"mood": "steady"}),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=tr,
        default_locale="ru",
    )
    await handler(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="пропускаю ли я?",
            user_id=USER,
            skill_id="analyze_adherence",
            for_date=None,
            is_peer_call=False,
        ),
        ("mood",),
    )
    snapshot("analyze_adherence", f"{llm.calls[0].system}\n===== USER =====\n{llm.calls[0].user}\n")


async def test_no_medications_finishes_without_llm_peers_or_memory() -> None:
    users = InMemoryUserSettings()
    users.seed(USER, locale="en")
    llm, peers, memory = FakeLLM(), FakePeerClient(), InMemoryVectorMemory()
    tr = JsonTranslator.from_dir(find_locales_dir())
    handler = AnalysisSkill(
        spec=MEDICATION_SPEC,
        mode="analyze_adherence",
        data=AdherenceData(tr, "ru"),
        llm=llm,
        uow=InMemoryUnitOfWorkFactory(
            {MedicationRepository: InMemoryMedications(), UserSettingsRepository: users}
        ),
        peers=peers,
        memory=memory,
        clock=FixedClock(NOW),
        translator=tr,
        default_locale="ru",
    )
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="analyse",
        user_id=USER,
        skill_id="analyze_adherence",
        for_date=None,
        is_peer_call=False,
    )
    assert (await handler(request, ("mood",))).output == "No active medications to analyse."
    assert llm.calls == []
    assert peers.calls == []
    assert memory.items == []
    assert MEDICATION_SPEC.memories is False
