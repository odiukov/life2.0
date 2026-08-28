"""Post-ingest HealthKit aggregator.

HealthKit gives us granular samples (per-stage sleep, per-second heart rate).
Our sleep and recovery agents read aggregated per-night `sleep_session`
and per-day `daily_stats` rows from `health_logs`. This module collapses raw
samples into those aggregate rows so the agents see a consistent schema
regardless of data source.

Runs at the end of every POST /sync/health, scoped to the authenticated user.
Idempotent — re-running on the same data overwrites the aggregated row with
identical content.

Sleep stage values (Apple HKCategoryValueSleepAnalysis):
  0 = inBed    (user put phone/watch in bed)
  1 = asleep   (iOS <16, now deprecated)
  2 = awake    (conscious during the night)
  3 = core     (light sleep)
  4 = deep
  5 = rem

Multi-source deduplication
--------------------------
Multiple integrations may write the same metric type (e.g. stepCount from
both Apple Watch and Garmin). The aggregator picks one authoritative source
per (type, day) using SOURCE_PRIORITY. For additive metrics, it sums within
the winning source and ignores others. This prevents double-counting when
future integrations (Garmin, Oura, Withings, etc.) are added.

Source naming convention (must be respected by all integrations):
  Direct API integrations  → lowercase slug: 'yazio', 'garmin', 'oura', etc.
  HealthKit app mirrors    → app display name as-is: 'Fitness', 'Yazio', 'Health'
  Our HealthKit sync       → device name from sourceRevision, fallback 'HealthKit'
  Sync-service paths       → 'apple_health'
  Aggregated rows          → 'HealthKit' (sleep_session / daily_stats)
"""
from __future__ import annotations

import logging
import re
from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

_STAGE_NAMES = {0: "inBed", 1: "asleep", 2: "awake", 3: "core", 4: "deep", 5: "rem"}
_ASLEEP_STAGES = {1, 3, 4, 5}  # not inBed, not awake

# ---------------------------------------------------------------------------
# Source priority (index 0 = highest priority).
# Direct API integrations beat HealthKit mirrors beat generic fallbacks.
# Extend this list as new integrations are added.
# ---------------------------------------------------------------------------
_SOURCE_PRIORITY: list[str] = [
    # Direct API integrations
    "garmin", "oura", "whoop", "polar", "withings", "eight_sleep", "eight-sleep",
    "yazio",
    # Dedicated device apps via HealthKit (most reliable hardware)
    "Garmin Connect", "Oura", "WHOOP", "Polar Flow",
    # Apple Watch (reliable wearable)
    "Fitness",
    # iPhone (pedometer only, lower accuracy)
    "iPhone", "Health",
    # Generic / our own sync tags
    "apple_health", "apple-health", "HealthKit",
]


def _source_rank(source: str) -> int:
    """Lower rank = higher priority. Unknown sources get a middle rank."""
    try:
        return _SOURCE_PRIORITY.index(source)
    except ValueError:
        # Unknown source: rank between dedicated device apps and iPhone
        return len(_SOURCE_PRIORITY) // 2


# ---------------------------------------------------------------------------
# Daily-stats metric definitions
# ---------------------------------------------------------------------------

# Sum raw samples per source, then take the best-source total.
# Prevents double-counting when multiple devices track the same cumulative metric.
_DAILY_SUM_TYPES = (
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

# Average across all samples from the best source.
_DAILY_AVG_TYPES = (
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

# Take the most recent sample from the best source (point-in-time measurements).
_DAILY_LATEST_TYPES = (
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


async def aggregate_for_user(user_id: UUID) -> dict:
    """Re-aggregate sleep + daily rows from raw HealthKit samples for user_id."""
    from shared.db import get_pool
    pool = await get_pool()
    counts = {"sleep_sessions": 0, "daily_stats": 0, "workouts": 0, "nutrition_days": 0}
    async with pool.acquire() as c:
        counts["sleep_sessions"] = await _rollup_sleep(c, user_id)
        counts["daily_stats"] = await _rollup_daily(c, user_id)
        counts["workouts"] = await _rollup_workouts(c, user_id)
        counts["nutrition_days"] = await _rollup_daily_nutrition(c, user_id)
    logger.info("healthkit aggregated user=%s → %s", user_id, counts)
    return counts


async def _rollup_sleep(c, user_id: UUID) -> int:
    rows = await c.fetch(
        """
        SELECT recorded_at, data, source
        FROM public.health_logs
        WHERE user_id = $1 AND type = 'sleepAnalysis'
        ORDER BY recorded_at
        """,
        user_id,
    )
    if not rows:
        return 0

    # Bucket per "night": a sample's night is the date of its start if
    # hour >= 18, otherwise date-minus-one. I.e. samples from the evening of
    # Mon 22:00 through Tue 11:59 all belong to night=Mon.
    per_night: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        start: datetime = r["recorded_at"]
        night_key = _night_of(start)
        per_night[night_key].append(dict(r))

    count = 0
    for night, samples in per_night.items():
        # Pick the best source for this night and use only its samples.
        best_source = min(
            {s["source"] or "HealthKit" for s in samples}, key=_source_rank
        )
        winning = [s for s in samples if (s["source"] or "HealthKit") == best_source]

        stages: dict[str, int] = defaultdict(int)
        total_asleep = 0
        earliest = None
        latest = None
        for s in winning:
            d = s["data"] or {}
            end_iso = d.get("end")
            if not end_iso:
                continue
            end = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
            start = s["recorded_at"]
            dur = int((end - start).total_seconds())
            if dur <= 0 or dur > 8 * 3600:
                continue
            stage_val = int(d.get("value", -1))
            stages[_STAGE_NAMES.get(stage_val, str(stage_val))] += dur
            if stage_val in _ASLEEP_STAGES:
                total_asleep += dur
            earliest = start if earliest is None or start < earliest else earliest
            latest = end if latest is None or end > latest else latest

        if total_asleep == 0:
            continue

        agg_payload = {
            "duration_seconds": total_asleep,
            "deep_sleep_seconds": stages.get("deep", 0),
            "rem_sleep_seconds": stages.get("rem", 0),
            "light_sleep_seconds": stages.get("core", 0) + stages.get("asleep", 0),
            "awake_seconds": stages.get("awake", 0),
            "stages": [{"kind": k, "seconds": v} for k, v in sorted(stages.items())],
            "source": best_source,
            "sleep_start": earliest.isoformat() if earliest else None,
            "sleep_end": latest.isoformat() if latest else None,
        }

        night_midnight = datetime.fromisoformat(night + "T00:00:00+00:00")
        await c.execute(
            """
            INSERT INTO public.health_logs (user_id, type, recorded_at, data, source, agent)
            VALUES ($1, 'sleep_session', $2, $3, 'HealthKit', 'sleep')
            ON CONFLICT (user_id, source, type, recorded_at) DO UPDATE
              SET data = EXCLUDED.data, agent = EXCLUDED.agent
            """,
            user_id, night_midnight, agg_payload,
        )
        count += 1
    return count


async def _rollup_daily(c, user_id: UUID) -> int:
    """One daily_stats row per calendar date with source deduplication.

    For each metric type on a given day, only the highest-priority source
    contributes to the aggregate. This prevents double-counting when multiple
    integrations (Apple Watch + Garmin, HealthKit mirror + direct API) both
    write the same metric.
    """
    all_types = list(_DAILY_SUM_TYPES) + list(_DAILY_AVG_TYPES) + list(_DAILY_LATEST_TYPES)
    rows = await c.fetch(
        """
        SELECT type, recorded_at, data, source
        FROM public.health_logs
        WHERE user_id = $1 AND type = ANY($2::text[])
        ORDER BY recorded_at
        """,
        user_id, all_types,
    )
    if not rows:
        return 0

    # Structure: per_day[day][type][source] = list of (recorded_at, value)
    per_day: dict[str, dict[str, dict[str, list[tuple[datetime, float]]]]] = (
        defaultdict(lambda: defaultdict(lambda: defaultdict(list)))
    )

    for r in rows:
        day_key = r["recorded_at"].astimezone(timezone.utc).date().isoformat()
        d = r["data"] or {}
        val = d.get("value")
        if val is None:
            continue
        try:
            fval = float(val)
        except (TypeError, ValueError):
            continue
        src = r["source"] or "HealthKit"
        per_day[day_key][r["type"]][src].append((r["recorded_at"], fval))

    count = 0
    for day, type_map in per_day.items():
        payload: dict[str, float] = {}

        for t in _DAILY_SUM_TYPES:
            if t not in type_map:
                continue
            # Sum per source, then pick the source with the highest total
            # (proxy for most complete coverage) among highest-priority sources.
            best_src = min(type_map[t].keys(), key=_source_rank)
            total = sum(v for _, v in type_map[t][best_src])
            if total > 0:
                payload[t] = round(total, 1)

        for t in _DAILY_AVG_TYPES:
            if t not in type_map:
                continue
            best_src = min(type_map[t].keys(), key=_source_rank)
            vals = [v for _, v in type_map[t][best_src]]
            if vals:
                payload[t] = round(sum(vals) / len(vals), 2)

        for t in _DAILY_LATEST_TYPES:
            if t not in type_map:
                continue
            best_src = min(type_map[t].keys(), key=_source_rank)
            # Latest sample from the best source
            latest_val = max(type_map[t][best_src], key=lambda x: x[0])[1]
            payload[t] = round(latest_val, 2)

        if not payload:
            continue

        # Use best source of the most important metric as the row's source tag
        representative_type = next(
            (t for t in _DAILY_SUM_TYPES if t in type_map),
            next(iter(type_map)),
        )
        row_source = min(type_map[representative_type].keys(), key=_source_rank)

        day_midnight = datetime.fromisoformat(day + "T00:00:00+00:00")
        await c.execute(
            """
            INSERT INTO public.health_logs (user_id, type, recorded_at, data, source, agent)
            VALUES ($1, 'daily_stats', $2, $3, $4, 'system')
            ON CONFLICT (user_id, source, type, recorded_at) DO UPDATE
              SET data = EXCLUDED.data
            """,
            user_id, day_midnight, payload, row_source,
        )
        count += 1
    return count


def _night_of(dt: datetime) -> str:
    """Return ISO date of the 'night' this sample belongs to.

    Evening (hour >= 18) → that day's date.
    Morning (hour < 18)  → previous day's date.
    """
    dt = dt.astimezone(timezone.utc)
    if dt.hour >= 18:
        return dt.date().isoformat()
    from datetime import timedelta
    return (dt - timedelta(days=1)).date().isoformat()


_WORKOUT_NAME_OVERRIDES: dict[str, str] = {
    "traditionalStrengthTraining": "Strength Training",
    "functionalStrengthTraining": "Functional Strength",
    "highIntensityIntervalTraining": "HIIT",
    "mixedMetabolicCardioTraining": "Cardio",
    "mixedCardio": "Cardio",
    "preparationAndRecovery": "Recovery",
    "mindAndBody": "Mind & Body",
}


def _format_workout_name(camel: str) -> str:
    if camel in _WORKOUT_NAME_OVERRIDES:
        return _WORKOUT_NAME_OVERRIDES[camel]
    spaced = re.sub(r"([A-Z])", r" \1", camel).strip()
    return spaced[0].upper() + spaced[1:] if spaced else "Workout"


async def _rollup_workouts(c, user_id: UUID) -> int:
    """Convert raw HK workout samples → agent='workout', type='activity' rows.

    The mobile sync uploads HKWorkout objects as type='workout', agent='apple-health'.
    This converts each one into the schema the workout agent and dashboard expect:
    agent='workout', type='activity', data={calories, distance_meters, activity_type, name}.
    Idempotent via ON CONFLICT.
    """
    rows = await c.fetch(
        """
        SELECT recorded_at, data, source
        FROM public.health_logs
        WHERE user_id = $1 AND agent = 'apple-health' AND type = 'workout'
        """,
        user_id,
    )
    if not rows:
        return 0

    count = 0
    for r in rows:
        d = r["data"] or {}
        raw_type = d.get("activityTypeName") or "workout"
        activity_data = {
            "calories": round(float(d.get("value") or 0)),
            "distance_meters": 0,
            "activity_type": raw_type,
            "name": _format_workout_name(raw_type),
        }
        src = r["source"] or "HealthKit"
        await c.execute(
            """
            INSERT INTO public.health_logs (user_id, type, recorded_at, data, source, agent)
            VALUES ($1, 'activity', $2, $3, $4, 'workout')
            ON CONFLICT (user_id, source, type, recorded_at) DO UPDATE
              SET data = EXCLUDED.data, agent = EXCLUDED.agent
            """,
            user_id, r["recorded_at"], activity_data, src,
        )
        count += 1
    return count


# Mapping from HealthKit dietary type → macro key in the meal totals dict
_DIETARY_TO_MACRO: dict[str, str] = {
    "dietaryEnergyConsumed": "kcal",
    "dietaryProtein": "protein_g",
    "dietaryCarbohydrates": "carbs_g",
    "dietaryFatTotal": "fat_g",
}


async def _rollup_daily_nutrition(c, user_id: UUID) -> int:
    """Sum HealthKit dietary samples per UTC day → agent='nutrition', type='meal' rows.

    Produces one daily-total meal row per day so the nutrition agent and dashboard
    see data even without Yazio. Idempotent via ON CONFLICT on source='apple_health'.
    """
    rows = await c.fetch(
        """
        SELECT type, recorded_at, data
        FROM public.health_logs
        WHERE user_id = $1 AND agent = 'apple-health'
          AND type = ANY($2::text[])
        ORDER BY recorded_at
        """,
        user_id, list(_DIETARY_TO_MACRO.keys()),
    )
    if not rows:
        return 0

    per_day: dict[str, dict[str, float]] = defaultdict(
        lambda: {"kcal": 0.0, "protein_g": 0.0, "carbs_g": 0.0, "fat_g": 0.0}
    )
    for r in rows:
        day_key = r["recorded_at"].astimezone(timezone.utc).date().isoformat()
        macro = _DIETARY_TO_MACRO.get(r["type"])
        if macro:
            per_day[day_key][macro] += float((r["data"] or {}).get("value") or 0)

    count = 0
    for day, totals in per_day.items():
        if totals["kcal"] == 0:
            continue
        meal_data = {
            "meal_type": "daily_total",
            "totals": {k: round(v, 1) for k, v in totals.items()},
            "items": [],
        }
        day_midnight = datetime.fromisoformat(day + "T00:00:00+00:00")
        await c.execute(
            """
            INSERT INTO public.health_logs (user_id, type, recorded_at, data, source, agent)
            VALUES ($1, 'meal', $2, $3, 'apple_health', 'nutrition')
            ON CONFLICT (user_id, source, type, recorded_at) DO UPDATE
              SET data = EXCLUDED.data
            """,
            user_id, day_midnight, meal_data,
        )
        count += 1
    return count
