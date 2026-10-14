from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from habits.application.data import HabitData
from habits.application.ports import HabitRepository
from habits.composition import HABITS_SPEC
from habits.domain.habit import Cadence, Habit, Kind
from habits.testing import InMemoryHabits
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
USER = UUID(int=12)


@pytest.mark.parametrize("consult", [("mood",), ()])
async def test_prompt_snapshot(snapshot, consult: tuple[str, ...]) -> None:  # type: ignore[no-untyped-def]
    habits, logs, users = InMemoryHabits(USER), InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(USER, timezone="Europe/Lisbon")
    uow = InMemoryUnitOfWorkFactory(
        {HabitRepository: habits, HealthLogRepository: logs, UserSettingsRepository: users}
    )
    async with uow.for_user(USER) as tx:
        hid = await tx.repo(HabitRepository).add(
            Habit(None, "meditation", Kind.BOOLEAN, Cadence.DAILY, (), None, None, None)
        )
    for i in (1, 2, 4):
        logs.seed(
            USER,
            HealthLogRow(
                "habit",
                NOW - timedelta(days=i),
                {"habit_id": str(hid), "name": "meditation", "completed": True},
                "manual",
                "habits",
            ),
        )
    llm = FakeLLM()
    llm.queue_text("ok")
    handler = AnalysisSkill(
        spec=HABITS_SPEC,
        mode="analyze_habit",
        data=HabitData(),
        llm=llm,
        uow=uow,
        peers=FakePeerClient({"mood": "calmer this week"}),
        memory=InMemoryVectorMemory(),
        clock=FixedClock(NOW),
        translator=JsonTranslator.from_dir(find_locales_dir()),
        default_locale="ru",
    )
    await handler(
        SkillRequest(
            task_id="t",
            context_id="c",
            text="как привычки?",
            user_id=USER,
            skill_id="analyze_habit",
            for_date=None,
            is_peer_call=False,
        ),
        consult,
    )
    snapshot(
        "analyze_habit" if consult else "analyze_habit_no_peers",
        f"{llm.calls[0].system}\n===== USER =====\n{llm.calls[0].user}\n",
    )
