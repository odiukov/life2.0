from datetime import UTC, datetime, timedelta
from uuid import uuid4
from zoneinfo import ZoneInfo

from habits.application.data import HabitData
from habits.application.ports import HabitRepository
from habits.domain.habit import Cadence, Habit, Kind
from habits.testing import InMemoryHabits
from shared.a2a.request import SkillRequest
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettings
from shared.testing.fakes import InMemoryHealthLogs, InMemoryUnitOfWorkFactory

NOW = datetime(2026, 10, 13, 20, 0, tzinfo=UTC)


async def test_sections_and_empty_tail() -> None:
    user = uuid4()
    habits, logs = InMemoryHabits(user), InMemoryHealthLogs()
    uow = InMemoryUnitOfWorkFactory({HabitRepository: habits, HealthLogRepository: logs})
    async with uow.for_user(user) as tx:
        hid = await tx.repo(HabitRepository).add(
            Habit(None, "gym", Kind.BOOLEAN, Cadence.WEEKLY, ("mon", "thu"), None, None, None)
        )
    request = SkillRequest(
        task_id="t",
        context_id="c",
        text="как привычки",
        user_id=user,
        skill_id="analyze_habit",
        for_date=None,
        is_peer_call=False,
    )
    async with uow.for_user(user) as tx:
        empty = await HabitData().load(tx, request, UserSettings(ZoneInfo("UTC"), None), NOW)
    assert empty.tail_override is not None
    assert "log a few days" in empty.tail_override
    logs.seed(
        user,
        HealthLogRow(
            "habit",
            NOW - timedelta(days=1),
            {"habit_id": str(hid), "name": "gym", "completed": True},
            "manual",
            "habits",
        ),
    )
    async with uow.for_user(user) as tx:
        loaded = await HabitData().load(tx, request, UserSettings(ZoneInfo("UTC"), None), NOW)
    active, checks, streaks = loaded.sections
    assert active.body == "- gym (boolean) | weekly: mon, thu"
    assert checks.body.startswith("- 2026-10-12 20:00 | gym")
    assert streaks.title == "Streaks"
    assert streaks.body == "- gym: current=1, longest(30d)=1"
