from datetime import UTC, datetime
from uuid import uuid4

import pytest
from habits.application.define import DefineHabit
from habits.application.ports import HabitRepository
from habits.application.schemas import HabitDefinition
from habits.domain.habit import Cadence, Kind
from habits.testing import InMemoryHabits
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


def test_schema_rules() -> None:
    d = HabitDefinition(
        name="Cold Shower!",
        kind="quantitative",
        cadence_type="weekly",
        cadence_days=["MON", "xyz", "fri"],
        target_value=3,
        unit="min",
    )
    assert (d.name, d.cadence_days) == ("cold-shower", ["mon", "fri"])
    assert (
        HabitDefinition(
            name="gym",
            kind="boolean",
            cadence_type="daily",
            cadence_days=["mon"],
            target_value=5,
            unit="x",
        ).cadence_days
        is None
    )
    with pytest.raises(ValueError, match="weekly habits need cadence_days"):
        HabitDefinition(name="gym", kind="boolean", cadence_type="weekly", cadence_days=["xyz"])
    with pytest.raises(ValueError, match="empty habit name"):
        HabitDefinition(name="  ", kind="boolean", cadence_type="daily")


async def test_create_duplicate_and_errors() -> None:
    user = uuid4()
    habits, users, llm = InMemoryHabits(user), InMemoryUserSettings(), FakeLLM()
    users.seed(user, locale="ru")
    handler = DefineHabit(
        llm=llm,
        uow=InMemoryUnitOfWorkFactory({HabitRepository: habits, UserSettingsRepository: users}),
        clock=FixedClock(datetime(2026, 10, 13, tzinfo=UTC)),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    req = SkillRequest(
        task_id="t",
        context_id="c",
        text="медитация 10 минут каждый день",
        user_id=user,
        skill_id="define_habit",
        for_date=None,
        is_peer_call=False,
    )
    llm.queue_structured(
        {
            "name": "meditation",
            "kind": "quantitative",
            "cadence_type": "daily",
            "target_value": 10,
            "unit": "min",
        }
    )
    assert (await handler(req, ())).output == "Слежу за привычкой «meditation» (каждый день)."
    [h] = habits.rows.values()
    assert (h.kind, h.cadence, h.target_value) == (Kind.QUANTITATIVE, Cadence.DAILY, 10.0)
    llm.queue_structured({"name": "meditation", "kind": "boolean", "cadence_type": "daily"})
    assert (await handler(req, ())).output == "Привычку «meditation» уже отслеживаю."
    llm.queue_structured(LLMInvalidOutput("{}", "bad"))
    assert (await handler(req, ())).output.startswith("Не понял")
    llm.queue_structured(LLMUnavailable("down"))
    assert (await handler(req, ())).failed
