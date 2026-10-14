from datetime import UTC, datetime
from uuid import uuid4

import pytest
from habits.application.archive import ArchiveHabit
from habits.application.ports import HabitRepository
from habits.application.streaks import StreakSummary
from habits.domain.habit import Cadence, Habit, Kind
from habits.testing import InMemoryHabits
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.config import find_locales_dir
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.testing.fakes import (
    FakeLLM,
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
    InMemoryVectorMemory,
)

NOW = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)
TR = JsonTranslator.from_dir(find_locales_dir())


@pytest.mark.parametrize("message", ["meditation", "убери медитацию"])
async def test_streak_summary_and_archive(message: str) -> None:
    user = uuid4()
    habits, logs, users = InMemoryHabits(user), InMemoryHealthLogs(), InMemoryUserSettings()
    users.seed(user, timezone="Europe/Lisbon", locale="ru")
    uow = InMemoryUnitOfWorkFactory(
        {HabitRepository: habits, HealthLogRepository: logs, UserSettingsRepository: users}
    )
    async with uow.for_user(user) as tx:
        med = await tx.repo(HabitRepository).add(
            Habit(None, "meditation", Kind.BOOLEAN, Cadence.DAILY, (), None, None, None)
        )
        await tx.repo(HabitRepository).add(
            Habit(None, "reading", Kind.QUANTITATIVE, Cadence.DAILY, (), 30, "pages", None)
        )
    for day in (11, 12, 13):
        logs.seed(
            user,
            HealthLogRow(
                "habit",
                datetime(2026, 10, day, 7, tzinfo=UTC),
                {"habit_id": str(med), "name": "meditation", "completed": True},
                "manual",
                "habits",
            ),
        )
    req = SkillRequest(
        task_id="t",
        context_id="c",
        text="",
        user_id=user,
        skill_id="get_streak_summary",
        for_date=None,
        is_peer_call=False,
    )
    summary = await StreakSummary(
        uow=uow, clock=FixedClock(NOW), translator=TR, default_locale="ru"
    )(req, ())
    assert summary.output == "✅ meditation — 3 дня · ⬜ reading — 0 дней (0/30 pages)"
    llm = FakeLLM()
    if message != "meditation":
        llm.queue_structured({"name": "meditation"})
    archive = ArchiveHabit(
        llm=llm,
        uow=uow,
        clock=FixedClock(NOW),
        translator=TR,
        memory=InMemoryVectorMemory(),
        default_locale="ru",
    )
    done = await archive(
        SkillRequest(
            task_id="t",
            context_id="c",
            text=message,
            user_id=user,
            skill_id="archive_habit",
            for_date=None,
            is_peer_call=False,
        ),
        (),
    )
    assert done.output == "Убрал привычку «meditation»."
    assert done.log_entry == "Убрал привычку «meditation»."
    empty = await StreakSummary(uow=uow, clock=FixedClock(NOW), translator=TR, default_locale="ru")(
        req, ()
    )
    assert empty.output.startswith("⬜ reading")
    assert len(llm.calls) == (0 if message == "meditation" else 1)
