from datetime import datetime, timezone


def map_sleep(date_str: str, raw: dict) -> dict | None:
    """Map Garmin get_sleep_data() response to a health_logs row dict."""
    dto = raw.get("dailySleepDTO", {})
    if not dto:
        return None
    start_ms = dto.get("sleepStartTimestampLocal")
    if start_ms is None:
        return None

    scores = dto.get("sleepScores", {})
    overall = scores.get("overall", {})
    score = overall.get("value") if isinstance(overall, dict) else None

    return {
        "agent": "sleep",
        "type": "sleep_session",
        "data": {
            "duration_seconds": dto.get("sleepTimeSeconds", 0),
            "start_time": datetime.fromtimestamp(start_ms / 1000).isoformat(),
            "end_time": datetime.fromtimestamp(
                dto.get("sleepEndTimestampLocal", start_ms) / 1000
            ).isoformat(),
            "score": score,
            "deep_sleep_seconds": dto.get("deepSleepSeconds", 0),
            "rem_sleep_seconds": dto.get("remSleepSeconds", 0),
            "light_sleep_seconds": dto.get("lightSleepSeconds", 0),
            "awake_seconds": dto.get("awakeSleepSeconds", 0),
            "hrv_weekly_avg": dto.get("averageHRV"),
        },
        "recorded_at": datetime.fromtimestamp(start_ms / 1000, tz=timezone.utc),
        "source": "garmin",
    }


def map_activity(raw: dict) -> dict | None:
    """Map a single Garmin activity dict to a health_logs row dict."""
    start_str = raw.get("startTimeLocal")
    if not start_str:
        return None

    recorded_at = datetime.fromisoformat(start_str).replace(tzinfo=timezone.utc)
    activity_type = raw.get("activityType", {})
    type_key = (
        activity_type.get("typeKey", "unknown")
        if isinstance(activity_type, dict)
        else "unknown"
    )

    return {
        "agent": "workout",
        "type": "activity",
        "data": {
            "activity_type": type_key,
            "name": raw.get("activityName", ""),
            "duration_seconds": int(raw.get("duration", 0)),
            "distance_meters": int(raw.get("distance", 0)),
            "calories": raw.get("calories", 0),
            "avg_hr": raw.get("averageHR"),
            "max_hr": raw.get("maxHR"),
            "garmin_activity_id": raw.get("activityId"),
        },
        "recorded_at": recorded_at,
        "source": "garmin",
    }


def map_daily_stats(date_str: str, raw: dict | None) -> dict | None:
    """Map Garmin get_stats() response to a health_logs row dict."""
    if not raw:
        return None

    recorded_at = datetime.fromisoformat(f"{date_str}T12:00:00").replace(
        tzinfo=timezone.utc
    )
    return {
        "agent": "sleep",
        "type": "daily_stats",
        "data": {
            "steps": raw.get("totalSteps", 0),
            "calories_active": raw.get("activeKilocalories", 0),
            "stress_avg": raw.get("averageStressLevel"),
            "body_battery_min": raw.get("minBodyBattery"),
            "body_battery_max": raw.get("maxBodyBattery"),
            "resting_hr": raw.get("restingHeartRate"),
        },
        "recorded_at": recorded_at,
        "source": "garmin",
    }
