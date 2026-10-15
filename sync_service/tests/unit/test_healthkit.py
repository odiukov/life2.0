from datetime import UTC, date, datetime, timedelta

from sync.domain.healthkit import (
    Sample,
    daily_rows,
    night_of,
    nutrition_rows,
    raw_row,
    sleep_rows,
    source_rank,
    touched_window,
    workout_rows,
)

T = datetime(2026, 10, 13, 22, 0, tzinfo=UTC)


def s(type_: str, start: datetime, **kw) -> Sample:
    return Sample(
        type=type_,
        start=start,
        end=kw.pop("end", None),
        value=kw.pop("value", None),
        unit=kw.pop("unit", None),
        stages=None,
        source=kw.pop("source", None),
        activity_type_name=kw.pop("name", None),
    )


def raws(*samples: Sample):
    return [raw_row(x) for x in samples]


def test_raw_rows_keep_the_legacy_shape() -> None:
    row = raw_row(
        s("stepCount", T, end=T + timedelta(minutes=5), value=120, unit="count", source="iPhone")
    )
    assert (row.agent, row.type, row.source, row.recorded_at) == (
        "apple-health",
        "stepCount",
        "iPhone",
        T,
    )
    assert row.data == {
        "end": (T + timedelta(minutes=5)).isoformat(),
        "value": 120.0,
        "unit": "count",
    }
    assert raw_row(s("stepCount", T, value=1)).source == "apple-health"


def test_priority_prefers_direct_integrations_and_ranks_unknowns_in_the_middle() -> None:
    assert (
        source_rank("garmin")
        < source_rank("Garmin Connect")
        < source_rank("Fitness")
        < source_rank("iPhone")
    )
    assert source_rank("Garmin Connect") < source_rank("SomeNewApp") < source_rank("iPhone")


def test_nights_start_at_18_utc() -> None:
    assert night_of(datetime(2026, 10, 13, 18, 0, tzinfo=UTC)) == date(2026, 10, 13)
    assert night_of(datetime(2026, 10, 14, 7, 0, tzinfo=UTC)) == date(2026, 10, 13)


def test_sleep_uses_only_the_best_source_and_skips_bad_intervals() -> None:
    watch = [
        s("sleepAnalysis", T, end=T + timedelta(hours=2), value=3, source="Fitness"),
        s(
            "sleepAnalysis",
            T + timedelta(hours=2),
            end=T + timedelta(hours=3),
            value=4,
            source="Fitness",
        ),
        s(
            "sleepAnalysis",
            T + timedelta(hours=3),
            end=T + timedelta(hours=3, minutes=10),
            value=2,
            source="Fitness",
        ),
        s(
            "sleepAnalysis", T, end=T + timedelta(hours=9), value=1, source="Fitness"
        ),  # > 8 h: skipped
    ]
    phone = [s("sleepAnalysis", T, end=T + timedelta(hours=7), value=1, source="iPhone")]
    (row,) = sleep_rows(raws(*watch, *phone))
    assert (row.type, row.agent, row.source, row.recorded_at) == (
        "sleep_session",
        "sleep",
        "HealthKit",
        datetime(2026, 10, 13, tzinfo=UTC),
    )
    assert row.data["duration_seconds"] == 3 * 3600
    assert row.data["deep_sleep_seconds"] == 3600
    assert row.data["awake_seconds"] == 600
    assert row.data["source"] == "Fitness"


def test_daily_sum_avg_latest_per_best_source() -> None:
    day = datetime(2026, 10, 13, 9, tzinfo=UTC)
    (row,) = daily_rows(
        raws(
            s("stepCount", day, value=4000, source="Fitness"),
            s("stepCount", day + timedelta(hours=2), value=3000.04, source="Fitness"),
            s("stepCount", day, value=9000, source="iPhone"),
            s("restingHeartRate", day, value=50, source="Fitness"),
            s("restingHeartRate", day + timedelta(hours=1), value=53, source="Fitness"),
            s("bodyMass", day, value=81.444, source="Health"),
            s("bodyMass", day + timedelta(hours=5), value=81.2, source="Health"),
        )
    )
    assert row.data == {"stepCount": 7000.0, "restingHeartRate": 51.5, "bodyMass": 81.2}
    assert (row.type, row.agent, row.source) == ("daily_stats", "system", "Fitness")


def test_workouts_and_dietary_totals() -> None:
    (activity,) = workout_rows(
        raws(s("workout", T, value=412.6, source="Fitness", name="traditionalStrengthTraining"))
    )
    assert (activity.type, activity.agent, activity.source) == ("activity", "workout", "Fitness")
    assert activity.data == {
        "calories": 413,
        "distance_meters": 0,
        "activity_type": "traditionalStrengthTraining",
        "name": "Strength Training",
    }
    (meal,) = nutrition_rows(
        raws(
            s("dietaryEnergyConsumed", T, value=500.04),
            s("dietaryProtein", T, value=30),
            s("dietaryEnergyConsumed", T + timedelta(hours=1), value=0),
        )
    )
    assert meal.data == {
        "meal_type": "daily_total",
        "totals": {"kcal": 500.0, "protein_g": 30.0, "carbs_g": 0.0, "fat_g": 0.0},
        "items": [],
    }
    assert (meal.source, meal.agent, meal.recorded_at) == (
        "apple_health",
        "nutrition",
        datetime(2026, 10, 13, tzinfo=UTC),
    )


def test_touched_window_covers_the_previous_night() -> None:
    start, end = touched_window([s("stepCount", datetime(2026, 10, 14, 3, tzinfo=UTC), value=1)])
    assert start == datetime(2026, 10, 12, 18, tzinfo=UTC)
    assert end == datetime(2026, 10, 15, 18, tzinfo=UTC)
