from datetime import UTC, datetime, timedelta
from pathlib import Path
from uuid import uuid4

from habits.application.attention import collect
from habits.application.ports import HabitRepository
from habits.domain.habit import Cadence, Habit, Kind
from habits.testing import InMemoryHabits
from shared.a2a.request import SkillRequest
from shared.adapters.i18n import JsonTranslator
from shared.attention import AttentionSkill
from shared.ports.health_logs import HealthLogRepository, HealthLogRow
from shared.ports.users import UserSettingsRepository
from shared.skill_ids import Attention
from shared.testing.attention_contract import assert_attention_contract
from shared.testing.fakes import (
    FixedClock,
    InMemoryHealthLogs,
    InMemoryUnitOfWorkFactory,
    InMemoryUserSettings,
)

TR = JsonTranslator.from_dir(Path(__file__).resolve().parents[4] / "packages" / "i18n" / "locales")
EVENING = datetime(2026, 10, 16, 16, 0, tzinfo=UTC)  # 19:00 Kyiv
USER = uuid4()
READ = Habit(uuid4(), "Read", Kind.BOOLEAN, Cadence.DAILY, (), None, None, None)
RUN = Habit(uuid4(), "Run", Kind.BOOLEAN, Cadence.DAILY, (), None, None, None)


def check(habit: Habit) -> HealthLogRow:
    return HealthLogRow(
        "habit", EVENING - timedelta(hours=2), {"habit_id": str(habit.id)}, "chat", "habits"
    )


async def run(*rows: HealthLogRow, now: datetime = EVENING) -> list[dict]:  # type: ignore[type-arg]
    logs, settings, habits = InMemoryHealthLogs(), InMemoryUserSettings(), InMemoryHabits(USER)
    settings.seed(USER, timezone="Europe/Kyiv")
    for habit in (READ, RUN):
        assert habit.id is not None
        habits.rows[habit.id] = habit
    for row in rows:
        logs.seed(USER, row)
    skill = AttentionSkill(
        uow=InMemoryUnitOfWorkFactory(
            {HealthLogRepository: logs, UserSettingsRepository: settings, HabitRepository: habits}
        ),
        clock=FixedClock(now),
        translator=TR,
        default_locale="en",
        collect=collect,
    )
    result = await skill(SkillRequest("t", "c", "", USER, Attention.ITEMS, None, False, {}), ())
    assert_attention_contract(result.data)
    return result.data["items"]  # type: ignore[index, return-value]


async def test_unchecked_habits_after_six_pm() -> None:
    [item] = await run(check(READ))
    assert (item["id"], item["text"], item["detail"]) == (
        "habits:due:2026-10-16",
        "1 habit left for today",
        "Run",
    )


async def test_nothing_before_six_pm_or_when_all_done() -> None:
    assert await run(now=datetime(2026, 10, 16, 10, 0, tzinfo=UTC)) == []
    assert await run(check(READ), check(RUN)) == []
