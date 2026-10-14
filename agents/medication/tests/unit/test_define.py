from datetime import UTC, datetime
from uuid import uuid4

from medication.application.define import DefineMedication
from medication.application.ports import MedicationRepository
from medication.testing import InMemoryMedications
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.llm import LLMInvalidOutput, LLMUnavailable
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FixedClock,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)


async def test_create_duplicate_and_errors() -> None:
    user, meds, users, llm = uuid4(), InMemoryMedications(), InMemoryUserSettings(), FakeLLM()
    users.seed(user, locale="ru")
    handler = DefineMedication(
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({MedicationRepository: meds, UserSettingsRepository: users}),
        clock=FixedClock(datetime(2026, 10, 13, tzinfo=UTC)),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    req = SkillRequest(
        task_id="t",
        context_id="c",
        text="витамин D 2000 МЕ каждое утро",
        user_id=user,
        skill_id="define_medication",
        for_date=None,
        is_peer_call=False,
    )
    llm.queue_structured({"name": "vitamin-d", "dose": "2000 IU", "schedule": "every morning"})
    assert (await handler(req, ())).output == "Отслеживаю «vitamin-d» 2000 IU · every morning."
    llm.queue_structured({"name": "vitamin-d", "schedule": "daily"})
    assert (await handler(req, ())).output == "«vitamin-d» уже отслеживаю."
    llm.queue_structured(LLMInvalidOutput("{}", "bad"))
    assert (await handler(req, ())).output.startswith("Не понял")
    llm.queue_structured(LLMUnavailable("down"))
    assert (await handler(req, ())).failed
