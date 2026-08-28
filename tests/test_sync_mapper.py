from datetime import datetime, timezone
import pytest
from sync_service.app.mapper import map_sleep, map_activity, map_daily_stats

SLEEP_RAW = {
    "dailySleepDTO": {
        "sleepTimeSeconds": 27180,
        "deepSleepSeconds": 5400,
        "lightSleepSeconds": 12600,
        "remSleepSeconds": 6300,
        "awakeSleepSeconds": 2880,
        "sleepStartTimestampLocal": 1744506900000,
        "sleepEndTimestampLocal": 1744531680000,
        "sleepScores": {"overall": {"value": 82}},
        "averageHRV": 54,
    }
}

ACTIVITY_RAW = {
    "activityId": 12345678,
    "activityName": "Morning Run",
    "activityType": {"typeKey": "running"},
    "duration": 2580.0,
    "distance": 5240.0,
    "calories": 412,
    "averageHR": 158,
    "maxHR": 181,
    "startTimeLocal": "2026-04-13 07:00:00",
}

STATS_RAW = {
    "totalSteps": 9823,
    "activeKilocalories": 620,
    "averageStressLevel": 28,
    "minBodyBattery": 14,
    "maxBodyBattery": 87,
    "restingHeartRate": 52,
}


def test_map_sleep_basic():
    row = map_sleep("2026-04-13", SLEEP_RAW)
    assert row is not None
    assert row["agent"] == "sleep"
    assert row["type"] == "sleep_session"
    assert row["source"] == "garmin"
    assert row["data"]["duration_seconds"] == 27180
    assert row["data"]["deep_sleep_seconds"] == 5400
    assert row["data"]["rem_sleep_seconds"] == 6300
    assert row["data"]["light_sleep_seconds"] == 12600
    assert row["data"]["awake_seconds"] == 2880
    assert row["data"]["score"] == 82
    assert row["data"]["hrv_weekly_avg"] == 54
    assert isinstance(row["recorded_at"], datetime)
    assert row["recorded_at"].tzinfo is not None


def test_map_sleep_missing_dto_returns_none():
    assert map_sleep("2026-04-13", {}) is None


def test_map_sleep_missing_start_returns_none():
    assert map_sleep("2026-04-13", {"dailySleepDTO": {}}) is None


def test_map_sleep_missing_optional_fields():
    raw = {
        "dailySleepDTO": {
            "sleepTimeSeconds": 25200,
            "sleepStartTimestampLocal": 1744506900000,
        }
    }
    row = map_sleep("2026-04-13", raw)
    assert row is not None
    assert row["data"]["score"] is None
    assert row["data"]["hrv_weekly_avg"] is None
    assert row["data"]["deep_sleep_seconds"] == 0


def test_map_activity_basic():
    row = map_activity(ACTIVITY_RAW)
    assert row is not None
    assert row["agent"] == "workout"
    assert row["type"] == "activity"
    assert row["source"] == "garmin"
    assert row["data"]["activity_type"] == "running"
    assert row["data"]["name"] == "Morning Run"
    assert row["data"]["duration_seconds"] == 2580
    assert row["data"]["distance_meters"] == 5240
    assert row["data"]["calories"] == 412
    assert row["data"]["avg_hr"] == 158
    assert row["data"]["max_hr"] == 181
    assert row["data"]["garmin_activity_id"] == 12345678
    assert isinstance(row["recorded_at"], datetime)
    assert row["recorded_at"].tzinfo is not None


def test_map_activity_missing_start_returns_none():
    assert map_activity({"activityName": "Run"}) is None


def test_map_activity_missing_optional_fields():
    raw = {"startTimeLocal": "2026-04-13 07:00:00"}
    row = map_activity(raw)
    assert row is not None
    assert row["data"]["activity_type"] == "unknown"
    assert row["data"]["avg_hr"] is None
    assert row["data"]["max_hr"] is None


def test_map_daily_stats_basic():
    row = map_daily_stats("2026-04-13", STATS_RAW)
    assert row is not None
    assert row["agent"] == "sleep"
    assert row["type"] == "daily_stats"
    assert row["source"] == "garmin"
    assert row["data"]["steps"] == 9823
    assert row["data"]["calories_active"] == 620
    assert row["data"]["stress_avg"] == 28
    assert row["data"]["body_battery_min"] == 14
    assert row["data"]["body_battery_max"] == 87
    assert row["data"]["resting_hr"] == 52
    assert isinstance(row["recorded_at"], datetime)
    assert row["recorded_at"].tzinfo is not None


def test_map_daily_stats_empty_returns_none():
    assert map_daily_stats("2026-04-13", {}) is None


def test_map_daily_stats_none_returns_none():
    assert map_daily_stats("2026-04-13", None) is None
