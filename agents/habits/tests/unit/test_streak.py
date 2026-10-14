from datetime import UTC, date, datetime
from uuid import UUID
from zoneinfo import ZoneInfo

import pytest
from habits.domain.habit import Cadence, Habit, HabitCheck, Kind
from habits.domain.streak import by_day, current_streak, day_complete, longest_streak, today_total

LISBON = ZoneInfo("Europe/Lisbon")
H = UUID(int=1)


def habit(**kw: object) -> Habit:
    values: dict[str, object] = {
        "id": H,
        "name": "meditation",
        "kind": Kind.BOOLEAN,
        "cadence": Cadence.DAILY,
        "cadence_days": (),
        "target_value": None,
        "unit": None,
        "created_at": None,
    }
    values.update(kw)
    return Habit(**values)  # type: ignore[arg-type]


def check(day: int, hour: int = 8, value: float | None = None) -> HabitCheck:
    return HabitCheck(
        habit_id=str(H),
        at=datetime(2026, 10, day, hour, tzinfo=UTC),
        value=value,
        unit=None,
        note=None,
    )


def test_days_follow_the_users_zone() -> None:
    late = HabitCheck(
        habit_id=str(H),
        at=datetime(2026, 10, 12, 23, 30, tzinfo=UTC),
        value=None,
        unit=None,
        note=None,
    )
    assert list(by_day([late], LISBON)) == [date(2026, 10, 13)]
    assert list(by_day([late], ZoneInfo("UTC"))) == [date(2026, 10, 12)]


@pytest.mark.parametrize(
    ("days", "today", "expected"),
    [
        ([10, 11, 12, 13], 13, 4),  # today done
        ([10, 11, 12], 13, 3),  # today pending: count from yesterday
        ([10, 12], 13, 1),  # gap on the 11th
        ([], 13, 0),
    ],
)
def test_daily_current_streak(days: list[int], today: int, expected: int) -> None:
    assert (
        current_streak(habit(), by_day([check(d) for d in days], LISBON), date(2026, 10, today))
        == expected
    )


def test_weekly_off_days_do_not_break_the_streak() -> None:
    mwf = habit(cadence=Cadence.WEEKLY, cadence_days=("mon", "wed", "fri"))
    # 2026-10-05 Mon, 07 Wed, 09 Fri, 12 Mon; today Tue 13 (not due)
    days = by_day([check(5), check(7), check(9), check(12)], LISBON)
    assert current_streak(mwf, days, date(2026, 10, 13)) == 4
    assert mwf.is_due(date(2026, 10, 12))
    assert not mwf.is_due(date(2026, 10, 13))


def test_quantitative_needs_the_target_in_one_day() -> None:
    pages = habit(kind=Kind.QUANTITATIVE, target_value=30, unit="pages")
    days = by_day([check(12, 8, 10), check(12, 20, 25), check(13, 8, 10)], LISBON)
    assert day_complete(pages, days[date(2026, 10, 12)])
    assert not day_complete(pages, days[date(2026, 10, 13)])
    assert today_total(pages, days[date(2026, 10, 13)]) == 10


def test_longest_streak_in_a_window() -> None:
    days = by_day([check(d) for d in (1, 2, 3, 5, 6, 7, 8, 10)], LISBON)
    assert longest_streak(habit(), days, date(2026, 10, 1), date(2026, 10, 13)) == 4


def test_weekly_due_today_pending_and_missed_due_day() -> None:
    mwf = habit(cadence=Cadence.WEEKLY, cadence_days=("mon", "wed", "fri"))
    grouped = by_day([check(d) for d in (5, 7, 9, 12)], LISBON)
    assert current_streak(mwf, grouped, date(2026, 10, 14)) == 4
    assert current_streak(mwf, grouped, date(2026, 10, 15)) == 0
    assert longest_streak(mwf, grouped, date(2026, 10, 5), date(2026, 10, 15)) == 4


def test_partial_quantitative_today_preserves_yesterdays_streak() -> None:
    pages = habit(kind=Kind.QUANTITATIVE, target_value=30, unit="pages")
    grouped = by_day([check(11, value=30), check(12, value=40), check(13, value=10)], LISBON)
    assert current_streak(pages, grouped, date(2026, 10, 13)) == 2
