"""Health Auto Export body-composition payloads → one `body_composition` row per local day."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from datetime import UTC, date, datetime
from typing import Any

from sync.domain.rows import Row

METRICS: Mapping[str, str] = {
    "Body Mass": "weight_kg",
    "Body Fat Percentage": "body_fat_pct",
    "Lean Body Mass": "lean_mass_kg",
    "Body Mass Index": "bmi",
    "Skeletal Muscle Mass": "skeletal_muscle_kg",
    "Bone Mass": "bone_mass_kg",
    # ViHealth-derived metrics (HealthKit-style names kept stable)
    "Basal Metabolic Rate": "bmr_kcal",
    "Visceral Fat Grade": "visceral_fat_grade",
    "Body Age": "body_age",
    "Body Score": "body_score",
    "Subcutaneous Fat Percentage": "subcutaneous_fat_pct",
    "Protein Mass": "protein_kg",
    "Body Water": "body_water_kg",
    "Muscle Mass": "muscle_kg",
    "Body Fat Mass": "body_fat_kg",
    "Fat Free Body Weight": "fat_free_kg",
}


def _parse(text: str) -> tuple[date, datetime] | None:
    """(local day as written in the payload, UTC instant). Format: "2026-04-14 09:37:16 +0300"."""
    try:
        local = datetime.strptime(text, "%Y-%m-%d %H:%M:%S %z")
    except ValueError:
        try:
            day = date.fromisoformat(text[:10])
        except ValueError:
            return None
        return day, datetime(day.year, day.month, day.day, tzinfo=UTC)
    return local.date(), local.astimezone(UTC)


def map_body_composition(entries: Iterable[Mapping[str, Any]]) -> list[Row]:
    metrics: dict[date, dict[str, float]] = {}
    first_seen: dict[date, datetime] = {}
    for entry in entries:
        key = METRICS.get(str(entry.get("name") or ""))
        value = entry.get("qty")
        parsed = _parse(str(entry.get("date") or ""))
        if key is None or parsed is None or not isinstance(value, int | float):
            continue
        day, instant = parsed
        first_seen.setdefault(day, instant)
        metrics.setdefault(day, {})[key] = round(float(value), 2)
    return [
        Row(
            agent="workout",
            type="body_composition",
            source="apple_health",
            recorded_at=first_seen[day],
            data=values,
        )
        for day, values in metrics.items()
    ]
