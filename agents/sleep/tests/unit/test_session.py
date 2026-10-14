from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from shared.ports.health_logs import HealthLogRow
from sleep.application.schemas import SleepExtraction
from sleep.domain.session import SleepSession, resolve_session, session_line

LISBON = ZoneInfo("Europe/Lisbon")
NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)  # 10:00 in Lisbon


def local(day: int, hh: int, mm: int = 0) -> datetime:
    return datetime(2026, 10, day, hh, mm, tzinfo=LISBON)


def test_bed_and_wake_cross_midnight() -> None:
    assert resolve_session(SleepExtraction(bed_time="23:30", wake_time="07:00"), NOW, LISBON) == (
        local(12, 23, 30),
        local(13, 7),
    )


def test_future_wake_time_means_yesterday() -> None:
    eight_am = datetime(2026, 10, 13, 7, 0, tzinfo=UTC)  # 08:00 Lisbon
    placed = resolve_session(
        SleepExtraction(wake_time="09:00", duration_minutes=480), eight_am, LISBON
    )
    assert placed == (local(12, 1), local(12, 9))
    assert placed[1] <= eight_am


def test_bed_time_and_duration() -> None:
    assert resolve_session(
        SleepExtraction(bed_time="00:30", duration_minutes=420), NOW, LISBON
    ) == (local(13, 0, 30), local(13, 7, 30))


def test_duration_only_ends_now() -> None:
    start, end = resolve_session(SleepExtraction(duration_minutes=420), NOW, LISBON)  # type: ignore[misc]
    assert end == NOW
    assert end - start == timedelta(hours=7)


def test_not_enough_to_place_the_night() -> None:
    assert resolve_session(SleepExtraction(wake_time="07:00"), NOW, LISBON) is None
    assert resolve_session(SleepExtraction(bed_time="23:00"), NOW, LISBON) is None
    assert resolve_session(SleepExtraction(quality=3), NOW, LISBON) is None


def test_dst_night_uses_real_elapsed_time() -> None:
    # 25 Oct 2026: Lisbon falls back at 02:00, so 23:00–07:00 lasts 9 hours.
    start, end = resolve_session(
        SleepExtraction(bed_time="23:00", wake_time="07:00"),
        datetime(2026, 10, 25, 9, 0, tzinfo=UTC),
        LISBON,
    )  # type: ignore[misc]
    assert end - start == timedelta(hours=9)


def test_from_row_reads_garmin_and_healthkit_keys() -> None:
    garmin = SleepSession.from_row(
        HealthLogRow(
            "sleep_session",
            NOW,
            {
                "duration_seconds": 25200,
                "deep_sleep_seconds": 3600,
                "start_time": "2026-10-12T23:40:00",
                "end_time": "2026-10-13T07:10:00",
                "score": 81,
                "hrv_weekly_avg": 44,
            },
            "garmin",
            "sleep",
        )
    )
    healthkit = SleepSession.from_row(
        HealthLogRow(
            "sleep_session",
            NOW,
            {
                "duration_seconds": 24000,
                "sleep_start": "2026-10-12T22:50:00+00:00",
                "sleep_end": "2026-10-13T06:00:00+00:00",
                "rem_sleep_seconds": 5400,
            },
            "HealthKit",
            "sleep",
        )
    )
    assert (garmin.duration_s, garmin.deep_s, garmin.score, garmin.hrv, garmin.source) == (
        25200,
        3600,
        81,
        44.0,
        "garmin",
    )
    assert (healthkit.rem_s, healthkit.start is not None, healthkit.source) == (
        5400,
        True,
        "HealthKit",
    )


def test_line_shows_day_source_and_present_fields() -> None:
    s = SleepSession.from_row(
        HealthLogRow(
            "sleep_session",
            datetime(2026, 10, 12, 22, 40, tzinfo=UTC),
            {"duration_seconds": 25200, "score": 81},
            "garmin",
            "sleep",
        )
    )
    assert session_line(s, LISBON) == "- 2026-10-12 | garmin | 7.0h | score=81"


def test_to_data_uses_garmin_keys() -> None:
    s = SleepSession(
        start=local(12, 23, 30),
        end=local(13, 7),
        duration_s=27000,
        deep_s=None,
        rem_s=None,
        light_s=None,
        awake_s=None,
        score=None,
        hrv=None,
        avg_hr=None,
        quality=4,
        source="chat",
    )
    assert s.to_data() == {
        "duration_seconds": 27000,
        "start_time": "2026-10-12T23:30:00+01:00",
        "end_time": "2026-10-13T07:00:00+01:00",
        "quality": 4,
    }


def test_bed_time_duration_cannot_end_in_future() -> None:
    assert (
        resolve_session(SleepExtraction(bed_time="09:00", duration_minutes=420), NOW, LISBON)
        is None
    )


def test_future_bed_time_is_placed_yesterday_and_returns_utc() -> None:
    placed = resolve_session(SleepExtraction(bed_time="23:30", duration_minutes=420), NOW, LISBON)
    assert placed is not None
    start, end = placed
    assert start == local(12, 23, 30)
    assert end == local(13, 6, 30)
    assert start.tzinfo is UTC
    assert end.tzinfo is UTC
    assert start < end <= NOW


def test_future_wake_with_bed_time_moves_whole_night_back() -> None:
    eight_am = datetime(2026, 10, 13, 7, tzinfo=UTC)
    assert resolve_session(
        SleepExtraction(bed_time="23:30", wake_time="09:00"), eight_am, LISBON
    ) == (local(11, 23, 30), local(12, 9))
