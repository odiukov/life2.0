"""Mapper for Apple Health body composition data.

Accepts the JSON format produced by the "Health Auto Export" iOS app:
{
    "data": [
        {"date": "2026-04-14 09:37:16 +0300", "qty": 79.6, "name": "Body Mass", "units": "kg"},
        {"date": "2026-04-14 09:37:16 +0300", "qty": 26.5, "name": "Body Fat Percentage", "units": "%"},
        ...
    ]
}

Supported metric names (Health Auto Export field names):
- Body Mass
- Body Fat Percentage
- Lean Body Mass
- Body Mass Index
- Skeletal Muscle Mass
- Bone Mass
"""

from datetime import datetime, timezone
from typing import Any


# Maps Apple Health metric names to our internal keys
_METRIC_MAP: dict[str, str] = {
    "Body Mass": "weight_kg",
    "Body Fat Percentage": "body_fat_pct",
    "Lean Body Mass": "lean_mass_kg",
    "Body Mass Index": "bmi",
    "Skeletal Muscle Mass": "skeletal_muscle_kg",
    "Bone Mass": "bone_mass_kg",
}


def _parse_date(date_str: str) -> datetime:
    """Parse Apple Health Export date string to UTC datetime."""
    # Format: "2026-04-14 09:37:16 +0300"
    try:
        return datetime.strptime(date_str, "%Y-%m-%d %H:%M:%S %z").astimezone(timezone.utc)
    except ValueError:
        # Fallback: date only
        return datetime.fromisoformat(date_str[:10]).replace(tzinfo=timezone.utc)


def map_body_composition(payload: dict[str, Any]) -> list[dict]:
    """Map Health Auto Export payload to health_logs rows.

    Groups metrics by date (day) into a single body_composition row.
    Returns a list of row dicts ready for insert_rows().
    """
    entries: list[dict] = payload.get("data", [])

    # Group by calendar date so one weigh-in = one row
    by_date: dict[str, dict] = {}
    by_date_dt: dict[str, datetime] = {}

    for entry in entries:
        metric_name = entry.get("name", "")
        internal_key = _METRIC_MAP.get(metric_name)
        if not internal_key:
            continue

        date_str = entry.get("date", "")
        if not date_str:
            continue

        dt = _parse_date(date_str)
        day_key = dt.date().isoformat()

        if day_key not in by_date:
            by_date[day_key] = {}
            by_date_dt[day_key] = dt

        value = entry.get("qty")
        if value is not None:
            by_date[day_key][internal_key] = round(float(value), 2)

    rows = []
    for day_key, metrics in by_date.items():
        if not metrics:
            continue
        rows.append({
            "agent": "workout",
            "type": "body_composition",
            "data": metrics,
            "recorded_at": by_date_dt[day_key],
            "source": "apple_health",
        })

    return rows
