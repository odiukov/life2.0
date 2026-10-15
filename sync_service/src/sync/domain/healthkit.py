"""HealthKit samples → raw rows and the per-night/per-day aggregates the agents read.

Ported from the legacy orchestrator. Day and night keys are UTC on purpose: the aggregated rows
already stored are keyed that way. Pure: no database, no clock.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Any

from sync.domain.rows import Row

RAW_AGENT = "apple-health"
STAGE_NAMES = {0: "inBed", 1: "asleep", 2: "awake", 3: "core", 4: "deep", 5: "rem"}
ASLEEP_STAGES = {1, 3, 4, 5}
SOURCE_PRIORITY = [
    "garmin",
    "oura",
    "whoop",
    "polar",
    "withings",
    "eight_sleep",
    "eight-sleep",
    "yazio",
    "Garmin Connect",
    "Oura",
    "WHOOP",
    "Polar Flow",
    "Fitness",
    "iPhone",
    "Health",
    "apple_health",
    "apple-health",
    "HealthKit",
]
DAILY_SUM_TYPES = (
    "stepCount",
    "activeEnergyBurned",
    "basalEnergyBurned",
    "distanceWalkingRunning",
    "distanceCycling",
    "distanceSwimming",
    "flightsClimbed",
    "exerciseTime",
    "swimmingStrokeCount",
    "pushCount",
    "timeInDaylight",
    "timesFallen",
)
DAILY_AVG_TYPES = (
    "restingHeartRate",
    "heartRateVariabilitySDNN",
    "oxygenSaturation",
    "respiratoryRate",
    "walkingSpeed",
    "walkingHeartRateAverage",
    "walkingDoubleSupportPercentage",
    "walkingAsymmetryPercentage",
    "walkingSteadiness",
    "vo2Max",
    "atrialFibrillationBurden",
    "physicalEffort",
)
DAILY_LATEST_TYPES = (
    "bodyMass",
    "bodyFatPercentage",
    "leanBodyMass",
    "bodyMassIndex",
    "waistCircumference",
    "height",
    "bloodGlucose",
    "bloodPressureSystolic",
    "bloodPressureDiastolic",
    "bodyTemperature",
    "sleepingWristTemperature",
)
WORKOUT_NAMES = {
    "traditionalStrengthTraining": "Strength Training",
    "functionalStrengthTraining": "Functional Strength",
    "highIntensityIntervalTraining": "HIIT",
    "mixedMetabolicCardioTraining": "Cardio",
    "mixedCardio": "Cardio",
    "preparationAndRecovery": "Recovery",
    "mindAndBody": "Mind & Body",
}
DIETARY_TO_MACRO = {
    "dietaryEnergyConsumed": "kcal",
    "dietaryProtein": "protein_g",
    "dietaryCarbohydrates": "carbs_g",
    "dietaryFatTotal": "fat_g",
}
RAW_TYPES = (
    "sleepAnalysis",
    "workout",
    *DAILY_SUM_TYPES,
    *DAILY_AVG_TYPES,
    *DAILY_LATEST_TYPES,
    *DIETARY_TO_MACRO,
)


def source_rank(source: str) -> int:
    """Lower is better. Unknown sources rank between dedicated device apps and the iPhone."""
    try:
        return SOURCE_PRIORITY.index(source)
    except ValueError:
        return len(SOURCE_PRIORITY) // 2


def night_of(ts: datetime) -> date:
    """Evening (≥ 18:00 UTC) belongs to that day's night; earlier hours to the previous day's."""
    utc = ts.astimezone(UTC)
    return utc.date() if utc.hour >= 18 else (utc - timedelta(days=1)).date()


def workout_name(camel: str) -> str:
    if camel in WORKOUT_NAMES:
        return WORKOUT_NAMES[camel]
    spaced = re.sub(r"([A-Z])", r" \1", camel).strip()
    return spaced[0].upper() + spaced[1:] if spaced else "Workout"


@dataclass(frozen=True, slots=True)
class Sample:
    type: str
    start: datetime
    end: datetime | None
    value: float | None
    unit: str | None
    stages: list[Mapping[str, Any]] | None
    source: str | None
    activity_type_name: str | None


def raw_row(sample: Sample) -> Row:
    """The legacy /sync/health row: data = the sample minus type/start/source, Nones dropped."""
    data: dict[str, Any] = {}
    if sample.end is not None:
        data["end"] = sample.end.isoformat()
    for key, value in (
        ("value", sample.value),
        ("unit", sample.unit),
        ("stages", sample.stages),
        ("activityTypeName", sample.activity_type_name),
    ):
        if value is not None:
            data[key] = value
    return Row(
        type=sample.type,
        recorded_at=sample.start,
        data=data,
        source=sample.source or RAW_AGENT,
        agent=RAW_AGENT,
    )


def _midnight(day: date) -> datetime:
    return datetime.combine(day, time.min, tzinfo=UTC)


def sleep_rows(raw: Iterable[Row]) -> list[Row]:
    per_night: dict[date, list[Row]] = defaultdict(list)
    for r in raw:
        if r.type == "sleepAnalysis":
            per_night[night_of(r.recorded_at)].append(r)
    out = []
    for night, samples in per_night.items():
        best = min({x.source or "HealthKit" for x in samples}, key=source_rank)
        stages: dict[str, int] = defaultdict(int)
        asleep = 0
        earliest = latest = None
        for x in sorted(
            (x for x in samples if (x.source or "HealthKit") == best), key=lambda x: x.recorded_at
        ):
            end_iso = x.data.get("end")
            if not end_iso:
                continue
            end = datetime.fromisoformat(str(end_iso).replace("Z", "+00:00"))
            duration = int((end - x.recorded_at).total_seconds())
            if duration <= 0 or duration > 8 * 3600:
                continue
            stage = int(x.data.get("value", -1))
            stages[STAGE_NAMES.get(stage, str(stage))] += duration
            if stage in ASLEEP_STAGES:
                asleep += duration
            earliest = x.recorded_at if earliest is None or x.recorded_at < earliest else earliest
            latest = end if latest is None or end > latest else latest
        if asleep == 0:
            continue
        out.append(
            Row(
                type="sleep_session",
                recorded_at=_midnight(night),
                source="HealthKit",
                agent="sleep",
                data={
                    "duration_seconds": asleep,
                    "deep_sleep_seconds": stages.get("deep", 0),
                    "rem_sleep_seconds": stages.get("rem", 0),
                    "light_sleep_seconds": stages.get("core", 0) + stages.get("asleep", 0),
                    "awake_seconds": stages.get("awake", 0),
                    "stages": [{"kind": k, "seconds": v} for k, v in sorted(stages.items())],
                    "source": best,
                    "sleep_start": earliest.isoformat() if earliest else None,
                    "sleep_end": latest.isoformat() if latest else None,
                },
            )
        )
    return out


def daily_rows(raw: Iterable[Row]) -> list[Row]:
    wanted = set(DAILY_SUM_TYPES) | set(DAILY_AVG_TYPES) | set(DAILY_LATEST_TYPES)
    per_day: dict[date, dict[str, dict[str, list[tuple[datetime, float]]]]] = defaultdict(
        lambda: defaultdict(lambda: defaultdict(list))
    )
    for r in raw:
        if r.type not in wanted or r.data.get("value") is None:
            continue
        try:
            value = float(r.data["value"])
        except (TypeError, ValueError):
            continue
        per_day[r.recorded_at.astimezone(UTC).date()][r.type][r.source or "HealthKit"].append(
            (r.recorded_at, value)
        )
    out = []
    for day, types in per_day.items():
        payload: dict[str, float] = {}
        for t in DAILY_SUM_TYPES:
            if t in types:
                total = sum(v for _, v in types[t][min(types[t], key=source_rank)])
                if total > 0:
                    payload[t] = round(total, 1)
        for t in DAILY_AVG_TYPES:
            if t in types:
                values = [v for _, v in types[t][min(types[t], key=source_rank)]]
                if values:
                    payload[t] = round(sum(values) / len(values), 2)
        for t in DAILY_LATEST_TYPES:
            if t in types:
                payload[t] = round(
                    max(types[t][min(types[t], key=source_rank)], key=lambda x: x[0])[1], 2
                )
        if not payload:
            continue
        representative = next((t for t in DAILY_SUM_TYPES if t in types), next(iter(types)))
        out.append(
            Row(
                type="daily_stats",
                recorded_at=_midnight(day),
                data=payload,
                source=min(types[representative], key=source_rank),
                agent="system",
            )
        )
    return out


def workout_rows(raw: Iterable[Row]) -> list[Row]:
    out = []
    for r in raw:
        if r.agent != RAW_AGENT or r.type != "workout":
            continue
        kind = str(r.data.get("activityTypeName") or "workout")
        out.append(
            Row(
                type="activity",
                recorded_at=r.recorded_at,
                source=r.source or "HealthKit",
                agent="workout",
                data={
                    "calories": round(float(r.data.get("value") or 0)),
                    "distance_meters": 0,
                    "activity_type": kind,
                    "name": workout_name(kind),
                },
            )
        )
    return out


def nutrition_rows(raw: Iterable[Row]) -> list[Row]:
    per_day: dict[date, dict[str, float]] = defaultdict(
        lambda: {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    )
    for r in raw:
        macro = DIETARY_TO_MACRO.get(r.type)
        if r.agent == RAW_AGENT and macro:
            per_day[r.recorded_at.astimezone(UTC).date()][macro] += float(r.data.get("value") or 0)
    return [
        Row(
            type="meal",
            recorded_at=_midnight(day),
            source="apple_health",
            agent="nutrition",
            data={
                "meal_type": "daily_total",
                "totals": {k: round(v, 1) for k, v in totals.items()},
                "items": [],
            },
        )
        for day, totals in per_day.items()
        if totals["kcal"] != 0
    ]


def touched_window(samples: Iterable[Sample]) -> tuple[datetime, datetime]:
    """All raw rows that can change the aggregates of the days this batch touched.

    Days are UTC; a night runs 18:00 → 18:00 UTC, so start at 18:00 two days before the earliest
    sample and end at 18:00 the day after the latest.
    """
    starts = [s.start.astimezone(UTC) for s in samples]
    first, last = min(starts).date(), max(starts).date()
    return (
        datetime.combine(first - timedelta(days=2), time(18), tzinfo=UTC),
        datetime.combine(last + timedelta(days=1), time(18), tzinfo=UTC),
    )
