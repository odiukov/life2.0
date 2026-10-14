"""Sanitized Garmin, Yazio and Health Auto Export payloads, shaped like the live APIs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

LISBON = ZoneInfo("Europe/Lisbon")
NEW_YORK = ZoneInfo("America/New_York")


def gmt_ms(when: datetime) -> int:
    """Garmin `…GMT` epoch: the real instant in milliseconds."""
    return int(when.astimezone(UTC).timestamp() * 1000)


def local_ms(when: datetime) -> int:
    """Garmin `…Local` epoch: the local wall time encoded as if it were UTC."""
    return int(when.replace(tzinfo=UTC).timestamp() * 1000)


def garmin_sleep(
    start: datetime, end: datetime, *, with_gmt: bool = True, **overrides: Any
) -> dict[str, Any]:
    dto: dict[str, Any] = {
        "sleepTimeSeconds": 27180,
        "deepSleepSeconds": 5400,
        "lightSleepSeconds": 12600,
        "remSleepSeconds": 6300,
        "awakeSleepSeconds": 2880,
        "sleepStartTimestampLocal": local_ms(start),
        "sleepEndTimestampLocal": local_ms(end),
        "sleepScores": {"overall": {"value": 82}},
        "averageHRV": 54,
        "avgHeartRate": 51,
    }
    if with_gmt:
        dto["sleepStartTimestampGMT"] = gmt_ms(start)
        dto["sleepEndTimestampGMT"] = gmt_ms(end)
    dto.update(overrides)
    return {"dailySleepDTO": dto}


ACTIVITY: dict[str, Any] = {
    "activityId": 12345678,
    "activityName": "Morning Run",
    "activityType": {"typeKey": "running"},
    "duration": 2580.0,
    "distance": 5240.0,
    "calories": 412,
    "averageHR": 158,
    "maxHR": 181,
    "startTimeLocal": "2026-10-13 07:00:00",
    "startTimeGMT": "2026-10-13 06:00:00",
}

STATS: dict[str, Any] = {
    "totalSteps": 9823,
    "activeKilocalories": 620,
    "averageStressLevel": 28,
    "minBodyBattery": 14,
    "maxBodyBattery": 87,
    "restingHeartRate": 52,
}

HRV: dict[str, Any] = {
    "hrvSummary": {
        "lastNightAvg": 47.6,
        "status": "BALANCED",
        "baseline": {"balancedLow": 41, "balancedUpper": 58},
    }
}

YAZIO_PRODUCT_ENTRY: dict[str, Any] = {"product_id": "p-oat", "amount": 80, "daytime": "breakfast"}
YAZIO_PRODUCT: dict[str, Any] = {
    "name": "Oatmeal",
    "nutrients": {
        "energy.energy": 3.7,
        "nutrient.protein": 0.13,
        "nutrient.carb": 0.6,
        "nutrient.fat": 0.07,
    },
}
YAZIO_SIMPLE_ENTRY: dict[str, Any] = {
    "name": "Борщ (AI)",
    "daytime": "lunch",
    "serving_quantity": 1,
    "is_ai_generated": True,
    "nutrients": {
        "energy.energy": 368,
        "nutrient.protein": 27,
        "nutrient.carb": 30,
        "nutrient.fat": 14,
    },
}
YAZIO_RECIPE_ENTRY: dict[str, Any] = {"recipe_id": "r-1", "portion_count": 2, "daytime": "dinner"}
YAZIO_RECIPE: dict[str, Any] = {
    "name": "Lasagne",
    "nutrients": {
        "energy.energy": 450,
        "nutrient.protein": 25,
        "nutrient.carb": 40,
        "nutrient.fat": 20,
    },
}

BODY_ENTRIES: list[dict[str, Any]] = [
    {"date": "2026-04-14 09:37:16 +0300", "qty": 79.6, "name": "Body Mass", "units": "kg"},
    {"date": "2026-04-14 09:37:16 +0300", "qty": 26.5, "name": "Body Fat Percentage", "units": "%"},
    {"date": "2026-04-14 09:37:16 +0300", "qty": 54.6, "name": "Lean Body Mass", "units": "kg"},
    {"date": "2026-04-14 09:37:16 +0300", "qty": 27.5, "name": "Body Mass Index", "units": "count"},
    {
        "date": "2026-04-14 09:37:16 +0300",
        "qty": 33.1,
        "name": "Skeletal Muscle Mass",
        "units": "kg",
    },
    {"date": "2026-04-14 09:37:16 +0300", "qty": 3.9, "name": "Bone Mass", "units": "kg"},
    {"date": "2026-03-01 08:00:00 +0000", "qty": 81.0, "name": "Body Mass", "units": "kg"},
    {"date": "2026-03-01 08:00:00 +0000", "qty": 28.1, "name": "Body Fat Percentage", "units": "%"},
    {"date": "2026-04-14 09:37:16 +0300", "qty": 120, "name": "Heart Rate", "units": "bpm"},
]
