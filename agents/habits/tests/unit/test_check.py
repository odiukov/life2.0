from datetime import UTC, datetime
from uuid import uuid4

from habits.application.check import CheckHabit
from habits.application.ports import HabitRepository
from habits.domain.habit import Cadence, Habit, Kind
from habits.testing import InMemoryHabits
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
    user = uuid4()
    habits, logs, users, llm = (
        InMemoryHabits(user),
        InMemoryHealthLogs(),
        InMemoryUserSettings(),
        FakeLLM(),
    )
    users.seed(user, timezone="Europe/Lisbon", locale="ru")
    uow = InMemoryUnitOfWorkFactory(
        {HabitRepository: habits, HealthLogRepository: logs, UserSettingsRepository: users}
    )
    async with uow.for_user(user) as tx:
        hid = await tx.repo(HabitRepository).add(
            Habit(None, "meditation", Kind.QUANTITATIVE, Cadence.DAILY, (), 10, "min", None)
        )
    handler = CheckHabit(
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
        skill_id="log_habit_check",
        for_date=None,
        is_peer_call=False,
        params=params or {},
    )
    return handler, llm, logs, request, hid


async def test_exact_name_needs_no_model_and_stores_legacy_keys() -> None:
    handler, llm, logs, request, hid = await env("meditation", {"value": "15"})
    result = await handler(request, ())
    [row] = logs.rows[request.user_id]
    assert (row.type, row.agent, row.source) == ("habit", "habits", "manual")
    assert row.data == {
        "habit_id": str(hid),
        "name": "meditation",
        "completed": True,
        "raw_text": "meditation",
        "source_skill": "log_habit_check",
        "value": 15.0,
        "unit": "min",
    }
    assert result.output == "Отметил «meditation»: 15 min."
    assert llm.calls == []
    assert result.log_entry == "meditation"


async def test_resolves_other_language_names_through_the_model() -> None:
    handler, llm, logs, request, _ = await env("отметь медитацию")
    llm.queue_structured({"name": "meditation"})
    assert (await handler(request, ())).output == "Отметил «meditation»."
    assert len(logs.rows[request.user_id]) == 1


async def test_habit_id_param_wins_and_unknown_is_not_found() -> None:
    handler, llm, logs, request, _hid = await env("whatever", {"habit_id": "nope"})
    llm.queue_structured({"name": None})
    assert (await handler(request, ())).output.startswith("Не нашёл")
    assert logs.rows == {}


async def test_id_takes_priority_over_name_and_model() -> None:
    handler, llm, logs, request, hid = await env("отметь медитацию", {"name": "unknown"})
    request.params["habit_id"] = str(hid)
    result = await handler(request, ())
    assert result.output == "Отметил «meditation»."
    assert llm.calls == []
    assert logs.rows[request.user_id][0].data["habit_id"] == str(hid)


async def test_model_cannot_choose_an_unlisted_habit() -> None:
    handler, llm, logs, request, _ = await env("отметь неизвестную привычку")
    llm.queue_structured({"name": "unlisted"})
    assert (await handler(request, ())).output.startswith("Не нашёл")
    assert logs.rows == {}
