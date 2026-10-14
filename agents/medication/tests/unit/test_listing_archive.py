from datetime import UTC, datetime
from uuid import uuid4

from medication.application.archive import ArchiveMedication
from medication.application.listing import ListActive
from medication.application.ports import MedicationRepository
from medication.domain.medication import Medication
from medication.testing import InMemoryMedications
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FixedClock,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)

TR = JsonTranslator.from_dir(find_locales_dir())


async def test_list_and_archive() -> None:
    user, meds, users = uuid4(), InMemoryMedications(), InMemoryUserSettings()
    users.seed(user, locale="ru")
    uow = InMemoryUnitOfWorkFactory({MedicationRepository: meds, UserSettingsRepository: users})
    async with uow.for_user(user) as tx:
        await tx.repo(MedicationRepository).add(
            Medication(None, "vitamin-d", "2000 IU", "every morning", None, None)
        )
        await tx.repo(MedicationRepository).add(
            Medication(None, "b12", None, "mon,wed,fri", None, None)
        )

    def req(text: str, skill: str) -> SkillRequest:
        return SkillRequest(
            task_id="t",
            context_id="c",
            text=text,
            user_id=user,
            skill_id=skill,
            for_date=None,
            is_peer_call=False,
        )

    listing = ListActive(uow=uow, translator=TR, default_locale="ru")
    assert (
        await listing(req("", "list_active"), ())
    ).output == "• vitamin-d 2000 IU · every morning\n• b12 · mon,wed,fri"
    archive = ArchiveMedication(
        llm=FakeLLM(),
        uow=uow,
        clock=FixedClock(datetime(2026, 10, 13, tzinfo=UTC)),
        translator=TR,
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    done = await archive(req("b12", "archive_medication"), ())
    assert done.output == "Убрал «b12» из списка."
    assert done.log_entry == done.output
    assert (
        await listing(req("", "list_active"), ())
    ).output == "• vitamin-d 2000 IU · every morning"


async def test_archive_resolves_russian_and_english_empty_list() -> None:
    user, meds, users, llm = uuid4(), InMemoryMedications(), InMemoryUserSettings(), FakeLLM()
    users.seed(user, locale="en")
    await meds.add(Medication(None, "vitamin-d", None, "daily", None, None))
    uow = InMemoryUnitOfWorkFactory({MedicationRepository: meds, UserSettingsRepository: users})
    archive = ArchiveMedication(
        llm=llm,
        uow=uow,
        clock=FixedClock(datetime(2026, 10, 13, tzinfo=UTC)),
        translator=TR,
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="больше не принимаю витамин д",
        user_id=user,
        skill_id="archive_medication",
        for_date=None,
        is_peer_call=False,
    )
    llm.queue_structured({"name": "vitamin-d"})
    assert (await archive(request, ())).output == "Removed “vitamin-d”."
    assert (await archive(request, ())).output == "I couldn't find that medication."
    listing = ListActive(uow=uow, translator=TR, default_locale="ru")
    assert (await listing(request, ())).output == "No active medications."
