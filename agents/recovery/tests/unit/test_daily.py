from datetime import UTC, date, datetime
from zoneinfo import ZoneInfo

from recovery.domain.daily import assemble_days, row_day
from shared.ports.health_logs import HealthLogRow

LISBON, NEW_YORK = ZoneInfo("Europe/Lisbon"), ZoneInfo("America/New_York")


def r(type_: str, at: datetime, source: str, **data: object) -> HealthLogRow:
    return HealthLogRow(type=type_, recorded_at=at, data=data, source=source, agent="sleep")


def test_healthkit_rows_keep_their_calendar_day_west_of_utc() -> None:
    midnight = datetime(2026, 10, 13, 0, 0, tzinfo=UTC)  # HealthKit's date marker
    assert row_day(r("sleep_session", midnight, "HealthKit"), NEW_YORK) == date(2026, 10, 13)
    assert row_day(r("daily_stats", midnight, "Apple Watch"), NEW_YORK) == date(2026, 10, 13)
    assert row_day(
        r("hrv_status", datetime(2026, 10, 13, 6, tzinfo=UTC), "garmin"), NEW_YORK
    ) == date(2026, 10, 13)


def test_timestamped_sessions_use_the_users_zone_not_kyiv() -> None:
    start = datetime(2026, 10, 12, 22, 30, tzinfo=UTC)  # 23:30 Lisbon, 01:30 Kyiv next day
    assert row_day(r("sleep_session", start, "garmin"), LISBON) == date(2026, 10, 12)


def test_garmin_and_healthkit_keys_and_hrv_preference() -> None:
    day = datetime(2026, 10, 13, 12, tzinfo=UTC)
    days = assemble_days(
        [
            r(
                "daily_stats",
                day,
                "garmin",
                resting_hr=52,
                stress_avg=31,
                body_battery_min=20,
                body_battery_max=88,
            ),
            r("hrv_status", day, "garmin", hrv_rmssd=48),
            r(
                "sleep_session",
                datetime(2026, 10, 13, 0, tzinfo=UTC),
                "HealthKit",
                duration_seconds=25200,
                awake_seconds=1800,
            ),
            r(
                "daily_stats",
                datetime(2026, 10, 14, 0, tzinfo=UTC),
                "Apple Watch",
                restingHeartRate=55,
                heartRateVariabilitySDNN=41.5,
            ),
        ],
        LISBON,
    )
    d13, d14 = days[date(2026, 10, 13)], days[date(2026, 10, 14)]
    assert (d13.rhr, d13.stress, d13.bb_min, d13.bb_max, d13.hrv, d13.hrv_source) == (
        52,
        31,
        20,
        88,
        48,
        "hrv_status",
    )
    assert (d13.sleep_duration_h, d13.sleep_efficiency_pct) == (7.0, 92.9)
    assert (d14.rhr, d14.hrv, d14.hrv_source) == (55, 41.5, "daily_stats")
    assert d14.metrics() == {
        "hrv_sdnn": 41.5,
        "rhr": 55,
        "sleep_efficiency_pct": None,
        "sleep_duration_h": None,
    }


def test_sleep_hrv_is_the_last_fallback() -> None:
    days = assemble_days(
        [
            r(
                "sleep_session",
                datetime(2026, 10, 12, 22, tzinfo=UTC),
                "garmin",
                duration_seconds=27000,
                hrv_weekly_avg=44,
                score=81,
            )
        ],
        LISBON,
    )
    d = days[date(2026, 10, 12)]
    assert (d.hrv, d.hrv_source, d.sleep_score) == (44, "sleep_session", 81)


def test_device_session_wins_over_chat_for_the_same_day() -> None:
    days = assemble_days(
        [
            r(
                "sleep_session",
                datetime(2026, 10, 12, 22, tzinfo=UTC),
                "chat",
                duration_seconds=36000,
            ),
            r(
                "sleep_session",
                datetime(2026, 10, 12, 22, 15, tzinfo=UTC),
                "garmin",
                duration_seconds=25200,
                awake_seconds=600,
            ),
        ],
        LISBON,
    )
    assert days[date(2026, 10, 12)].sleep_duration_h == 7.0


def test_chat_session_counts_when_no_device_row_exists() -> None:
    days = assemble_days(
        [
            r(
                "sleep_session",
                datetime(2026, 10, 12, 22, tzinfo=UTC),
                "chat",
                duration_seconds=28800,
            )
        ],
        LISBON,
    )
    assert days[date(2026, 10, 12)].sleep_duration_h == 8.0
