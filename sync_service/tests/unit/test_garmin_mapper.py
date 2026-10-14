from datetime import UTC, date, datetime

from sync.domain.garmin import (
    GarminBundle,
    map_activity,
    map_daily_stats,
    map_garmin,
    map_hrv,
    map_sleep,
)
from sync_fixtures import ACTIVITY, HRV, LISBON, NEW_YORK, STATS, garmin_sleep

DAY = date(2026, 10, 13)


def test_sleep_uses_gmt_timestamps_and_stores_offsets() -> None:
    start = datetime(2026, 10, 12, 23, 40, tzinfo=LISBON)  # 22:40 UTC
    end = datetime(2026, 10, 13, 7, 10, tzinfo=LISBON)
    row = map_sleep(DAY, garmin_sleep(start, end), LISBON)
    assert row is not None
    assert (row.agent, row.type, row.source) == ("sleep", "sleep_session", "garmin")
    assert row.recorded_at == datetime(2026, 10, 12, 22, 40, tzinfo=UTC)
    assert row.data["start_time"] == "2026-10-12T23:40:00+01:00"
    assert row.data["end_time"] == "2026-10-13T07:10:00+01:00"
    assert row.data == {
        "duration_seconds": 27180,
        "start_time": "2026-10-12T23:40:00+01:00",
        "end_time": "2026-10-13T07:10:00+01:00",
        "score": 82,
        "deep_sleep_seconds": 5400,
        "rem_sleep_seconds": 6300,
        "light_sleep_seconds": 12600,
        "awake_seconds": 2880,
        "hrv_weekly_avg": 54,
        "avg_hr": 51,
    }


def test_sleep_without_gmt_reads_local_epochs_in_the_users_zone() -> None:
    start = datetime(2026, 10, 12, 23, 0, tzinfo=NEW_YORK)  # 03:00 UTC on the 13th
    end = datetime(2026, 10, 13, 6, 30, tzinfo=NEW_YORK)
    row = map_sleep(DAY, garmin_sleep(start, end, with_gmt=False), NEW_YORK)
    assert row is not None
    assert row.recorded_at == datetime(2026, 10, 13, 3, 0, tzinfo=UTC)
    assert row.data["start_time"] == "2026-10-12T23:00:00-04:00"


def test_sleep_across_the_dst_change_keeps_the_real_length() -> None:
    # Lisbon leaves summer time at 02:00 on 2026-10-25: the night is one hour longer than the wall clock says.
    start = datetime(2026, 10, 24, 23, 30, tzinfo=LISBON)  # 22:30 UTC
    end = datetime(2026, 10, 25, 7, 0, tzinfo=LISBON)  # 07:00 UTC
    row = map_sleep(date(2026, 10, 25), garmin_sleep(start, end, with_gmt=False), LISBON)
    assert row is not None
    assert row.recorded_at == datetime(2026, 10, 24, 22, 30, tzinfo=UTC)
    assert (row.data["start_time"], row.data["end_time"]) == (
        "2026-10-24T23:30:00+01:00",
        "2026-10-25T07:00:00+00:00",
    )
    started = datetime.fromisoformat(row.data["start_time"])
    ended = datetime.fromisoformat(row.data["end_time"])
    assert (ended - started).total_seconds() == 8.5 * 3600


def test_sleep_without_a_session_is_skipped() -> None:
    assert map_sleep(DAY, {}, LISBON) is None
    assert map_sleep(DAY, None, LISBON) is None
    assert (
        map_sleep(
            DAY,
            {"dailySleepDTO": {"sleepTimeSeconds": None, "sleepStartTimestampGMT": None}},
            LISBON,
        )
        is None
    )


def test_sleep_tolerates_missing_optional_fields() -> None:
    start = datetime(2026, 10, 12, 23, 40, tzinfo=LISBON)
    raw = {"dailySleepDTO": {"sleepStartTimestampGMT": int(start.timestamp() * 1000)}}
    row = map_sleep(DAY, raw, LISBON)
    assert row is not None
    assert row.data["duration_seconds"] == 0
    assert row.data["score"] is None
    assert row.data["end_time"] == row.data["start_time"]


def test_activity_uses_gmt_start_and_falls_back_to_local_wall_time() -> None:
    row = map_activity(ACTIVITY, LISBON)
    assert row is not None
    assert (row.agent, row.type, row.source) == ("workout", "activity", "garmin")
    assert row.recorded_at == datetime(2026, 10, 13, 6, 0, tzinfo=UTC)
    assert row.data == {
        "activity_type": "running",
        "name": "Morning Run",
        "duration_seconds": 2580,
        "distance_meters": 5240,
        "calories": 412,
        "avg_hr": 158,
        "max_hr": 181,
        "garmin_activity_id": 12345678,
    }
    local_only = {k: v for k, v in ACTIVITY.items() if k != "startTimeGMT"}
    row = map_activity(local_only, NEW_YORK)
    assert row is not None
    assert row.recorded_at == datetime(2026, 10, 13, 11, 0, tzinfo=UTC)


def test_activity_without_start_or_with_nulls() -> None:
    assert map_activity({"activityName": "x"}, LISBON) is None
    row = map_activity(
        {
            "startTimeGMT": "2026-10-13 06:00:00",
            "duration": None,
            "distance": None,
            "activityType": None,
        },
        LISBON,
    )
    assert row is not None
    assert (
        row.data["activity_type"],
        row.data["duration_seconds"],
        row.data["distance_meters"],
    ) == ("unknown", 0, 0)


def test_daily_stats_and_hrv_keep_calendar_day_keys() -> None:
    stats = map_daily_stats(DAY, STATS)
    assert stats is not None
    assert stats.recorded_at == datetime(2026, 10, 13, 12, 0, tzinfo=UTC)
    assert stats.data == {
        "steps": 9823,
        "calories_active": 620,
        "stress_avg": 28,
        "body_battery_min": 14,
        "body_battery_max": 87,
        "resting_hr": 52,
    }
    assert map_daily_stats(DAY, {}) is None
    assert map_daily_stats(DAY, None) is None
    hrv = map_hrv(DAY, HRV)
    assert hrv is not None
    assert (hrv.agent, hrv.type, hrv.recorded_at) == (
        "sleep",
        "hrv_status",
        datetime(2026, 10, 13, 6, 0, tzinfo=UTC),
    )
    assert hrv.data == {
        "hrv_rmssd": 47,
        "status": "BALANCED",
        "baseline_low": 41,
        "baseline_high": 58,
    }
    assert map_hrv(DAY, {"hrvSummary": {}}) is None
    assert map_hrv(DAY, None) is None


def test_bundle_maps_every_part() -> None:
    start = datetime(2026, 10, 12, 23, 40, tzinfo=LISBON)
    bundle = GarminBundle(
        sleep=((DAY, garmin_sleep(start, start.replace(day=13, hour=7))), (date(2026, 10, 12), {})),
        activities=(ACTIVITY,),
        stats=((DAY, STATS),),
        hrv=((DAY, HRV),),
        failures=("hrv 2026-10-12",),
    )
    assert sorted(r.type for r in map_garmin(bundle, LISBON)) == [
        "activity",
        "daily_stats",
        "hrv_status",
        "sleep_session",
    ]


def test_sleep_overlap_defaults_to_first_occurrence_but_gmt_preserves_fold() -> None:
    # These two instants have the same local wall time. Only GMT identifies the second one.
    first = datetime(2026, 11, 1, 1, 30, tzinfo=NEW_YORK, fold=0)
    second = first.replace(fold=1)
    fallback = map_sleep(first.date(), garmin_sleep(second, second, with_gmt=False), NEW_YORK)
    assert fallback is not None
    assert fallback.recorded_at == datetime(2026, 11, 1, 5, 30, tzinfo=UTC)
    assert fallback.data["start_time"] == "2026-11-01T01:30:00-04:00"
    authoritative = map_sleep(second.date(), garmin_sleep(second, second), NEW_YORK)
    assert authoritative is not None
    assert authoritative.recorded_at == datetime(2026, 11, 1, 6, 30, tzinfo=UTC)
    assert authoritative.data["start_time"] == "2026-11-01T01:30:00-05:00"
