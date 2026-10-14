from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from shared.ports.health_logs import HealthLogRow
from workout.domain.workout import Workout, resolve_start, workout_line

LISBON = ZoneInfo("Europe/Lisbon")
NOW = datetime(2026, 10, 13, 17, 0, tzinfo=UTC)  # 18:00 Lisbon


def test_start_defaults_to_now_minus_duration() -> None:
    assert resolve_start(None, 30, NOW, LISBON) == NOW - timedelta(minutes=30)


def test_stated_start_today_or_yesterday_if_in_the_future() -> None:
    assert resolve_start("07:30", 45, NOW, LISBON) == datetime(2026, 10, 13, 6, 30, tzinfo=UTC)
    assert resolve_start("19:00", 45, NOW, LISBON) == datetime(2026, 10, 12, 18, 0, tzinfo=UTC)


def test_from_row_garmin_and_healthkit() -> None:
    garmin = Workout.from_row(
        HealthLogRow(
            "activity",
            NOW,
            {
                "activity_type": "running",
                "name": "Lisbon Run",
                "duration_seconds": 1800,
                "distance_meters": 5200,
                "calories": 410,
                "avg_hr": 151,
            },
            "garmin",
            "workout",
        )
    )
    healthkit = Workout.from_row(
        HealthLogRow(
            "activity",
            NOW,
            {"activity_type": "traditionalStrengthTraining", "name": "Strength", "calories": 250},
            "Apple Watch",
            "workout",
        )
    )
    assert (garmin.distance_m, garmin.avg_hr, garmin.duration_s) == (5200.0, 151.0, 1800)
    assert (healthkit.activity_type, healthkit.duration_s, healthkit.source) == (
        "traditionalStrengthTraining",
        None,
        "Apple Watch",
    )


def test_line() -> None:
    w = Workout.from_row(
        HealthLogRow(
            "activity",
            NOW,
            {
                "activity_type": "running",
                "duration_seconds": 1800,
                "distance_meters": 5200,
                "avg_hr": 151,
            },
            "garmin",
            "workout",
        )
    )
    assert (
        workout_line(w, LISBON) == "- 2026-10-13 | garmin | running | 30 min | 5.2 km | avg_hr=151"
    )
