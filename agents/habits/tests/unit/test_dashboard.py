from habits.application.dashboard import card, detail
from habits.application.ports import HabitRepository
from habits.domain.habit import Cadence, Habit, Kind
from habits.testing import InMemoryHabits
from shared.skill_ids import Dashboard
from shared.testing import dashboard_golden as g


def habits_repo() -> InMemoryHabits:
    repo = InMemoryHabits(g.USER_ID)
    for row in g.habit_rows():
        target = row.get("target_value")
        repo.rows[row["id"]] = Habit(  # type: ignore[index]
            id=row["id"],  # type: ignore[arg-type]
            name=str(row["name"]),
            kind=Kind(str(row["kind"])),
            cadence=Cadence(str(row["cadence_type"])),
            cadence_days=tuple(row.get("cadence_days") or ()),  # type: ignore[arg-type]
            target_value=float(target) if target is not None else None,  # type: ignore[arg-type]
            unit=row.get("unit"),  # type: ignore[arg-type]
            created_at=row["created_at"],  # type: ignore[arg-type]
        )
    return repo


async def test_card_matches_the_golden() -> None:
    assert await g.golden_call(
        card, Dashboard.CARD, {HabitRepository: habits_repo()}
    ) == g.expected_card("habits")


async def test_detail_matches_the_golden() -> None:
    assert await g.golden_call(
        detail, Dashboard.DETAIL, {HabitRepository: habits_repo()}
    ) == g.expected_detail("habits")
