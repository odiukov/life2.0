from datetime import UTC, datetime
from uuid import uuid4

from medication.application.intake import LogIntake
from medication.application.ports import MedicationRepository
from medication.domain.medication import Medication
from medication.testing import InMemoryMedications
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)

NOW = datetime(2026, 10, 13, 8, 0, tzinfo=UTC)


async def env(text: str, params: dict[str, object] | None = None):  # type: ignore[no-untyped-def]
    user, meds, logs, users, llm = (
        uuid4(),
        InMemoryMedications(),
        InMemoryHealthLogs(),
        InMemoryUserSettings(),
        FakeLLM(),
    )
    users.seed(user, timezone="Europe/Lisbon", locale="ru")
    uow = InMemoryUnitOfWorkFactory(
        {MedicationRepository: meds, HealthLogRepository: logs, UserSettingsRepository: users}
    )
    async with uow.for_user(user) as tx:
        await tx.repo(MedicationRepository).add(
            Medication(None, "vitamin-d", "2000 IU", "every morning", None, None)
        )
        await tx.repo(MedicationRepository).add(
            Medication(None, "b12", None, "mon,wed,fri", None, None)
        )
    handler = LogIntake(
        llm=llm,
        uow=uow,
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text=text,
        user_id=user,
        skill_id="log_medication",
        for_date=None,
        is_peer_call=False,
        params=params or {},
    )
    return handler, llm, logs, request


async def test_free_text_intake_resolves_the_medication() -> None:
    handler, llm, logs, request = await env("принял витамин д")
    llm.queue_structured({"name": "vitamin-d"})
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert (row.type, row.agent, row.source, row.data["name"], row.data["dose_at_time"]) == (
        "medication_taken",
        "medication",
        "manual",
        "vitamin-d",
        "2000 IU",
    )
    assert result.output == "Отметил приём: vitamin-d 2000 IU."
    assert result.log_entry == result.output


async def test_name_param_and_dose_override_need_no_model() -> None:
    handler, llm, logs, request = await env("whatever", {"name": "B12", "dose_override": "500 mcg"})
    result = await handler(request, ())
    assert llm.calls == []
    assert logs.rows[request.user_id][0].data["dose_at_time"] == "500 mcg"
    assert result.output == "Отметил приём: b12 500 mcg."


async def test_unknown_medication() -> None:
    handler, llm, logs, request = await env("принял аспирин")
    llm.queue_structured({"name": None})
    assert (await handler(request, ())).output.startswith("Не нашёл")
    assert logs.rows == {}


async def test_source_note_and_raw_text_are_preserved() -> None:
    handler, llm, logs, request = await env(
        "took b12", {"name": "b12", "source": "voice", "note": "with food"}
    )
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert row.source == "voice"
    assert row.data == {
        "name": "b12",
        "medication_id": row.data["medication_id"],
        "dose_at_time": None,
        "note": "with food",
        "raw_text": "took b12",
        "source_skill": "log_medication",
    }
    assert result.log_recorded_at == NOW
    assert llm.calls == []


async def test_resolver_rejects_model_name_outside_active_list() -> None:
    handler, llm, logs, request = await env("принял аспирин")
    llm.queue_structured({"name": "aspirin"})
    assert (await handler(request, ())).output.startswith("Не нашёл")
    assert logs.rows == {}
