from datetime import UTC, date, datetime, time, timedelta, timezone, tzinfo
from zoneinfo import ZoneInfo

import pytest
from nutrition.application.models import BodyComposition, UserProfile
from nutrition.domain.day import day_window, local_today, resolve_eaten_at, resolve_zone
from nutrition.domain.meal import (
    CHAT_SOURCE,
    YAZIO_SOURCE,
    Macros,
    Meal,
    MealItem,
    MealType,
    total_intake,
)
from shared.domain.energy import BodyProfile, calorie_goal

LISBON = ZoneInfo("Europe/Lisbon")


class MissingOffset(tzinfo):
    def utcoffset(self, dt: datetime | None) -> None:
        return None


def item(name: str, kcal: float) -> MealItem:
    return MealItem(
        name=name, amount_g=100, macros=Macros(kcal=kcal, protein_g=1, carbs_g=2, fat_g=3)
    )


def test_meal_totals_are_the_sum_of_all_item_macros() -> None:
    meal = Meal.from_items(
        recorded_at=datetime(2026, 10, 13, 8, tzinfo=UTC),
        items=(item("omelette", 300), item("toast", 120)),
        meal_type=MealType.BREAKFAST,
        source=CHAT_SOURCE,
    )
    assert meal.totals == Macros(kcal=420, protein_g=2, carbs_g=4, fat_g=6)
    assert total_intake(iter([meal, meal])) == Macros(kcal=840, protein_g=4, carbs_g=8, fat_g=12)


def test_empty_meals_and_intake_have_zero_macros() -> None:
    meal = Meal.from_items(
        recorded_at=datetime(2026, 10, 13, tzinfo=UTC),
        items=(),
        meal_type=None,
        source=YAZIO_SOURCE,
    )
    assert meal.totals == Macros()
    assert total_intake([]) == Macros()


@pytest.mark.parametrize("offset", [None, MissingOffset()])
def test_meal_creation_rejects_timestamps_without_an_offset(offset: tzinfo | None) -> None:
    when = datetime(2026, 10, 13, 8, tzinfo=offset)
    with pytest.raises(ValueError, match="timezone"):
        Meal.from_items(recorded_at=when, items=(), meal_type=None, source=CHAT_SOURCE)
    with pytest.raises(ValueError, match="timezone"):
        Meal(recorded_at=when, items=(), totals=Macros(), meal_type=None, source=CHAT_SOURCE)


def test_rescheduling_meal_preserves_contents_and_leaves_original_unchanged() -> None:
    original = Meal.from_items(
        recorded_at=datetime(2026, 10, 13, 8, tzinfo=UTC),
        items=(item("toast", 120),),
        meal_type=MealType.BREAKFAST,
        source=CHAT_SOURCE,
    )
    when = datetime(2026, 10, 12, 22, tzinfo=UTC)
    updated = original.with_recorded_at(when)
    assert updated.recorded_at == when
    assert updated.items == original.items
    assert updated.totals == Macros(kcal=120, protein_g=1, carbs_g=2, fat_g=3)
    assert updated.meal_type == MealType.BREAKFAST
    assert updated.source == CHAT_SOURCE
    assert original.recorded_at == datetime(2026, 10, 13, 8, tzinfo=UTC)


def test_rescheduling_meal_rejects_naive_time() -> None:
    meal = Meal.from_items(
        recorded_at=datetime(2026, 10, 13, tzinfo=UTC),
        items=(),
        meal_type=None,
        source=CHAT_SOURCE,
    )
    with pytest.raises(ValueError, match="timezone"):
        meal.with_recorded_at(datetime(2026, 10, 12))


@pytest.mark.parametrize("name", [None, "", "Mars/Olympus", 42, "../UTC", "/etc/localtime"])
def test_bad_timezones_fall_back_to_utc(name: object) -> None:
    assert resolve_zone(name) == ZoneInfo("UTC")


def test_valid_timezone_is_used() -> None:
    assert local_today(
        datetime(2026, 10, 12, 23, 30, tzinfo=UTC), resolve_zone("Europe/Lisbon")
    ) == date(2026, 10, 13)


@pytest.mark.parametrize(
    ("day", "start", "end", "hours"),
    [
        (
            date(2026, 10, 25),
            datetime(2026, 10, 24, 23, tzinfo=UTC),
            datetime(2026, 10, 26, tzinfo=UTC),
            25,
        ),
        (
            date(2026, 3, 29),
            datetime(2026, 3, 29, tzinfo=UTC),
            datetime(2026, 3, 29, 23, tzinfo=UTC),
            23,
        ),
        (
            date(2026, 10, 13),
            datetime(2026, 10, 12, 23, tzinfo=UTC),
            datetime(2026, 10, 13, 23, tzinfo=UTC),
            24,
        ),
    ],
)
def test_day_windows_span_local_midnights_in_utc(
    day: date, start: datetime, end: datetime, hours: int
) -> None:
    actual_start, actual_end = day_window(day, LISBON)
    assert actual_start == start
    assert actual_end == end
    assert actual_start.tzinfo is UTC
    assert actual_end.tzinfo is UTC
    assert actual_end - actual_start == timedelta(hours=hours)
    next_start, _ = day_window(day + timedelta(days=1), LISBON)
    assert actual_end == next_start


def test_local_today_uses_the_zone_not_utc() -> None:
    assert local_today(datetime(2026, 10, 12, 23, 30, tzinfo=UTC), LISBON) == date(2026, 10, 13)


def test_eaten_at_later_than_now_means_yesterday() -> None:
    now = datetime(2026, 10, 12, 23, 30, tzinfo=UTC)  # 00:30 local on the 13th
    assert resolve_eaten_at(now, LISBON, time(23)) == datetime(2026, 10, 12, 22, tzinfo=UTC)


@pytest.mark.parametrize(
    ("eaten_at", "expected"),
    [
        (time(8, 30), datetime(2026, 10, 13, 7, 30, tzinfo=UTC)),
        (time(13), datetime(2026, 10, 13, 12, tzinfo=UTC)),
    ],
)
def test_eaten_at_earlier_or_equal_to_now_is_today(eaten_at: time, expected: datetime) -> None:
    assert resolve_eaten_at(datetime(2026, 10, 13, 12, tzinfo=UTC), LISBON, eaten_at) == expected


def test_missing_eaten_at_returns_the_current_instant_in_utc() -> None:
    now = datetime(2026, 10, 13, 13, tzinfo=timezone(timedelta(hours=1)))
    resolved = resolve_eaten_at(now, LISBON, None)
    assert resolved == datetime(2026, 10, 13, 12, tzinfo=UTC)
    assert resolved.tzinfo is UTC


def test_dst_repeated_hour_compares_instants_instead_of_wall_times() -> None:
    now = datetime(2026, 10, 25, 1, 15, tzinfo=LISBON, fold=1)
    # First 01:30 happened 45 minutes before second 01:15.
    assert resolve_eaten_at(now, LISBON, time(1, 30)) == datetime(2026, 10, 25, 0, 30, tzinfo=UTC)


@pytest.mark.parametrize("offset", [None, MissingOffset()])
def test_day_helpers_reject_now_without_an_offset(offset: tzinfo | None) -> None:
    now = datetime(2026, 10, 13, tzinfo=offset)
    with pytest.raises(ValueError, match="timezone"):
        local_today(now, LISBON)
    with pytest.raises(ValueError, match="timezone"):
        resolve_eaten_at(now, LISBON, time(8))
    with pytest.raises(ValueError, match="timezone"):
        resolve_eaten_at(now, LISBON, None)


def test_default_profile_has_utc_and_an_unknown_calorie_goal() -> None:
    profile = UserProfile.default()
    assert profile.timezone == ZoneInfo("UTC")
    assert profile.locale is None
    assert profile.body == BodyProfile()
    composition = BodyComposition(
        recorded_at=datetime(2026, 10, 13, tzinfo=UTC),
        weight_kg=None,
        body_fat_pct=None,
        bmr_kcal=None,
    )
    assert (
        calorie_goal(
            profile.body, measured_bmr_kcal=composition.bmr_kcal, weight_kg=composition.weight_kg
        )
        is None
    )
