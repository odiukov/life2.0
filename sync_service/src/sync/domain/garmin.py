"""Garmin Connect payloads → health_logs rows.

Garmin gives two epochs per instant: `…GMT` is the real instant, `…Local` is the device's wall time
encoded as if it were UTC. Real instants are stored as UTC `recorded_at`; `start_time`/`end_time`
are ISO strings with the user's offset. Without GMT, an ambiguous local wall time uses the
first occurrence (fold=0); its historical offset cannot be inferred from that local epoch alone. Daily stats and HRV keep their calendar-day keys
(12:00 and 06:00 UTC), which 3a's recovery assembly relies on.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time
from typing import Any
from zoneinfo import ZoneInfo

from sync.domain.rows import Row

SOURCE = "garmin"
Payload = Mapping[str, Any]


@dataclass(frozen=True, slots=True)
class GarminBundle:
    sleep: tuple[tuple[date, Payload], ...] = ()
    activities: tuple[Payload, ...] = ()
    stats: tuple[tuple[date, Payload], ...] = ()
    hrv: tuple[tuple[date, Payload], ...] = ()
    failures: tuple[str, ...] = ()


def _epoch(value: object) -> float | None:
    return (
        float(value) / 1000
        if isinstance(value, int | float) and not isinstance(value, bool)
        else None
    )


def _instant(gmt: object, local: object, zone: ZoneInfo) -> datetime | None:
    if (seconds := _epoch(gmt)) is not None:
        return datetime.fromtimestamp(seconds, UTC)
    if (seconds := _epoch(local)) is not None:
        wall = datetime.fromtimestamp(seconds, UTC).replace(tzinfo=None)
        return wall.replace(tzinfo=zone, fold=0).astimezone(UTC)
    return None


def _wall(text: object, zone: ZoneInfo) -> datetime | None:
    if not isinstance(text, str) or not text:
        return None
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=zone) if parsed.tzinfo is None else parsed


def map_sleep(day: date, raw: Payload | None, zone: ZoneInfo) -> Row | None:
    dto = (raw or {}).get("dailySleepDTO") or {}
    start = _instant(dto.get("sleepStartTimestampGMT"), dto.get("sleepStartTimestampLocal"), zone)
    if start is None:
        return None
    end = (
        _instant(dto.get("sleepEndTimestampGMT"), dto.get("sleepEndTimestampLocal"), zone) or start
    )
    overall = (dto.get("sleepScores") or {}).get("overall")
    return Row(
        agent="sleep",
        type="sleep_session",
        source=SOURCE,
        recorded_at=start,
        data={
            "duration_seconds": dto.get("sleepTimeSeconds") or 0,
            "start_time": start.astimezone(zone).isoformat(),
            "end_time": end.astimezone(zone).isoformat(),
            "score": overall.get("value") if isinstance(overall, Mapping) else None,
            "deep_sleep_seconds": dto.get("deepSleepSeconds") or 0,
            "rem_sleep_seconds": dto.get("remSleepSeconds") or 0,
            "light_sleep_seconds": dto.get("lightSleepSeconds") or 0,
            "awake_seconds": dto.get("awakeSleepSeconds") or 0,
            "hrv_weekly_avg": dto.get("averageHRV"),
            "avg_hr": dto.get("avgHeartRate"),
        },
    )


def map_activity(raw: Payload, zone: ZoneInfo) -> Row | None:
    gmt = _wall(raw.get("startTimeGMT"), ZoneInfo("UTC"))
    start = gmt if gmt is not None else _wall(raw.get("startTimeLocal"), zone)
    if start is None:
        return None
    kind = raw.get("activityType")
    return Row(
        agent="workout",
        type="activity",
        source=SOURCE,
        recorded_at=start.astimezone(UTC),
        data={
            "activity_type": kind.get("typeKey", "unknown")
            if isinstance(kind, Mapping)
            else "unknown",
            "name": raw.get("activityName") or "",
            "duration_seconds": int(raw.get("duration") or 0),
            "distance_meters": int(raw.get("distance") or 0),
            "calories": raw.get("calories") or 0,
            "avg_hr": raw.get("averageHR"),
            "max_hr": raw.get("maxHR"),
            "garmin_activity_id": raw.get("activityId"),
        },
    )


def map_daily_stats(day: date, raw: Payload | None) -> Row | None:
    if not raw:
        return None
    return Row(
        agent="sleep",
        type="daily_stats",
        source=SOURCE,
        recorded_at=datetime.combine(day, time(12), UTC),
        data={
            "steps": raw.get("totalSteps") or 0,
            "calories_active": raw.get("activeKilocalories") or 0,
            "stress_avg": raw.get("averageStressLevel"),
            "body_battery_min": raw.get("minBodyBattery"),
            "body_battery_max": raw.get("maxBodyBattery"),
            "resting_hr": raw.get("restingHeartRate"),
        },
    )


def map_hrv(day: date, raw: Payload | None) -> Row | None:
    summary = (raw or {}).get("hrvSummary") or {}
    last_night = summary.get("lastNightAvg") or summary.get("lastNight")
    if not isinstance(last_night, int | float):
        return None
    baseline = summary.get("baseline") or {}
    return Row(
        agent="sleep",
        type="hrv_status",
        source=SOURCE,
        recorded_at=datetime.combine(day, time(6), UTC),
        data={
            "hrv_rmssd": int(last_night),
            "status": summary.get("status"),
            "baseline_low": baseline.get("balancedLow"),
            "baseline_high": baseline.get("balancedUpper"),
        },
    )


def map_garmin(bundle: GarminBundle, zone: ZoneInfo) -> list[Row]:
    rows = [map_sleep(day, raw, zone) for day, raw in bundle.sleep]
    rows += [map_activity(raw, zone) for raw in bundle.activities]
    rows += [map_daily_stats(day, raw) for day, raw in bundle.stats]
    rows += [map_hrv(day, raw) for day, raw in bundle.hrv]
    return [row for row in rows if row is not None]
