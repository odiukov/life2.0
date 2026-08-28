"""Per-agent detail builders: history + metrics + formula insight.

Public API: get_agent_detail(agent_id, user_id) -> dict
"""
from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from uuid import UUID

logger = logging.getLogger(__name__)

VALID_AGENT_IDS = frozenset(
    ["sleep", "workout", "nutrition", "mood", "habits", "recovery", "medication", "finance", "calendar"]
)


# ── Formula insight helpers (pure, no DB) ────────────────────────────────────


def _sleep_insight(history: list[dict], metrics: dict) -> str:
    values = [h["value"] for h in history if h["value"] > 0]
    if len(values) < 3:
        return ""
    avg = sum(values[:-1]) / len(values[:-1])
    last = values[-1]
    above_count = sum(1 for v in values[-3:] if v > avg)
    parts = []
    if above_count >= 2:
        parts.append(f"Above weekly average {above_count} of last 3 nights.")
    elif last < avg - 0.5:
        parts.append(f"Below weekly average by {avg - last:.1f}h last night.")
    return " ".join(parts)


def _workout_insight(history: list[dict], metrics: dict) -> str:
    active = [h for h in history if h["value"] > 0]
    if not active:
        return ""
    n = len(active)
    if n == 1:
        return "1 workout this week."
    return f"{n} workouts this week."


def _nutrition_insight(history: list[dict], metrics: dict) -> str:
    protein_g = metrics.get("protein_g")
    protein_goal = metrics.get("protein_goal_g")
    if protein_g is not None and protein_goal and protein_g < protein_goal * 0.8:
        deficit = int(protein_goal - protein_g)
        return f"Protein below goal by {deficit}g today."
    values = [h["value"] for h in history if h["value"] > 0]
    if len(values) < 3:
        return ""
    avg = sum(values) / len(values)
    goal = metrics.get("goal_kcal") or avg
    days_over = sum(1 for v in values if v >= goal * 0.9)
    if days_over >= 5:
        return f"On track {days_over} of {len(values)} days."
    return ""


def _nutrition_day_bounds(now: datetime | None = None) -> tuple[datetime, datetime]:
    """Yazio diary rows are stored on their source date as UTC meal slots."""
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    day_start = datetime(now_utc.year, now_utc.month, now_utc.day, tzinfo=timezone.utc)
    return day_start, day_start + timedelta(days=1)


def _format_nutrition_meal(row: dict) -> dict:
    data = row.get("data") or {}
    meal_type = str(data.get("meal_type") or "meal")
    items = [
        str(item.get("name"))
        for item in data.get("items") or []
        if isinstance(item, dict) and item.get("name")
    ]
    totals = data.get("totals") or {}
    recorded_at = row.get("recorded_at")
    return {
        "meal_type": meal_type,
        "label": meal_type.replace("_", " ").title(),
        "items": items,
        "kcal": int(round(float(totals.get("kcal") or 0))),
        "recorded_at": recorded_at.isoformat() if hasattr(recorded_at, "isoformat") else recorded_at,
    }


def _mood_insight(history: list[dict], metrics: dict) -> str:
    values = [h["value"] for h in history if h["value"] > 0]
    if len(values) < 4:
        return ""
    mid = len(values) // 2
    first_avg = sum(values[:mid]) / mid
    last_avg = sum(values[mid:]) / len(values[mid:])
    diff = last_avg - first_avg
    if diff > 0.5:
        return f"Score trending up +{diff:.1f} pts over the last {len(values)} days."
    if diff < -0.5:
        return f"Score trending down {diff:.1f} pts over the last {len(values)} days."
    return "Mood stable over the last week."


def _habits_insight(history: list[dict], metrics: dict) -> str:
    streak = metrics.get("streak", 0)
    rate = metrics.get("completion_7d", 0.0)
    missed = metrics.get("missed_names") or []
    parts = []
    if streak >= 3:
        parts.append(f"{streak}-day streak.")
    if missed:
        names = ", ".join(missed[:2])
        suffix = " and more" if len(missed) > 2 else ""
        parts.append(f"Missed: {names}{suffix}.")
    elif rate >= 0.8:
        parts.append(f"{int(rate * 100)}% completion this week.")
    return " ".join(parts)


def _recovery_insight(history: list[dict], metrics: dict) -> str:
    bucket = metrics.get("bucket", "unknown")
    if bucket == "unknown":
        return ""
    if bucket == "recovered":
        return "3 of 4 metrics above baseline. Ready to train."
    if bucket == "depleted":
        return "3 of 4 metrics below baseline. Prioritize rest today."
    return "Recovery metrics near baseline. Moderate training ok."


def _medication_insight(history: list[dict], metrics: dict) -> str:
    missed = metrics.get("missed_names") or []
    adherence = metrics.get("adherence_7d", 1.0)
    if not missed and adherence >= 0.95:
        return "Full adherence this week. Keep it up."
    if missed:
        names = ", ".join(missed[:3])
        suffix = " and more" if len(missed) > 3 else ""
        n = sum(1 for h in history if h["value"] == 0)
        return f"Missed {n} day(s) this week: {names}{suffix}."
    return f"{int(adherence * 100)}% adherence this week."


def _finance_insight(history: list[dict], metrics: dict) -> str:
    values = [h["value"] for h in history]
    if len(values) < 4:
        return ""
    mid = len(values) // 2
    first_avg = sum(values[:mid]) / mid if mid else 0
    last_avg = sum(values[mid:]) / len(values[mid:]) if values[mid:] else 0
    if first_avg == 0:
        return ""
    pct = ((last_avg - first_avg) / first_avg) * 100
    cat = metrics.get("top_category", "")
    cat_str = f" Top: {cat}." if cat else ""
    if pct > 15:
        return f"Spending up {pct:.0f}% vs earlier this week.{cat_str}"
    if pct < -15:
        return f"Spending down {abs(pct):.0f}% vs earlier this week.{cat_str}"
    cat_str2 = f"Top category: {cat}." if cat else ""
    return cat_str2


def _format_calendar_event(ev: dict) -> dict | None:
    from .calendar_context import _parse_iso_local

    if ev.get("all_day"):
        return {
            "time": "All day",
            "name": ev.get("summary") or "All-day event",
            "dur": "",
            "all_day": True,
        }
    start = _parse_iso_local(ev.get("start", ""))
    end = _parse_iso_local(ev.get("end", ""))
    if start is None or end is None:
        return None
    minutes = max(0, int((end - start).total_seconds() // 60))
    dur = f"{minutes // 60}h" if minutes and minutes % 60 == 0 else f"{minutes}m"
    return {
        "time": start.strftime("%H:%M"),
        "name": ev.get("summary") or "Untitled",
        "dur": dur,
        "start": start.isoformat(),
        "end": end.isoformat(),
        "all_day": False,
    }


def _calendar_insight(metrics: dict) -> str:
    events_count = metrics.get("events_count") or 0
    if events_count == 0:
        return "No calendar events found today."
    free_start = metrics.get("first_free_slot_start")
    free_len = metrics.get("first_free_slot_len_min")
    if free_start and free_len:
        return f"First free block starts at {free_start} for {free_len} minutes."
    return f"{events_count} event(s) on the calendar today."


# ── Per-agent builders ────────────────────────────────────────────────────────


async def _sleep_detail(user_id: UUID) -> dict:
    from .db import fetch_sleep_history
    from .db import get_pool
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta

    history = await fetch_sleep_history(user_id, days=7)

    kyiv = ZoneInfo("Europe/Kyiv")
    now_kyiv = datetime.now(kyiv)
    day_start = datetime(now_kyiv.year, now_kyiv.month, now_kyiv.day, tzinfo=kyiv) - timedelta(days=1)
    pool = await get_pool()
    # 36h lookback gives slack for late Garmin sync while taking the most recent session
    row = await pool.fetchrow(
        """
        SELECT
            (data->>'deep_sleep_seconds')::int AS deep_sec,
            (data->>'hrv_weekly_avg')::float AS hrv,
            (data->>'duration_seconds')::int AS dur_sec
        FROM health_logs
        WHERE user_id = $1 AND agent = 'sleep' AND type = 'sleep_session'
          AND recorded_at >= $2
        ORDER BY recorded_at DESC LIMIT 1
        """,
        user_id, day_start - timedelta(hours=36),
    )
    metrics: dict = {}
    if row:
        dur_sec = row["dur_sec"] or 0
        deep_sec = row["deep_sec"] or 0
        metrics["deep_hours"] = round(deep_sec / 3600, 2)
        metrics["hrv"] = int(row["hrv"]) if row["hrv"] else None
        efficiency = round((deep_sec / dur_sec * 100)) if dur_sec else None
        metrics["efficiency_pct"] = efficiency

    return {
        "agent": "sleep",
        "insight": _sleep_insight(history, metrics),
        "metrics": {k: v for k, v in metrics.items() if v is not None},
        "history": history,
    }


async def _workout_detail(user_id: UUID) -> dict:
    from .db import fetch_workout_history
    from .db import get_pool
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta

    history = await fetch_workout_history(user_id, days=7)

    kyiv = ZoneInfo("Europe/Kyiv")
    now_kyiv = datetime.now(kyiv)
    day_start = datetime(now_kyiv.year, now_kyiv.month, now_kyiv.day, tzinfo=kyiv) - timedelta(days=1)
    day_end = day_start + timedelta(days=1)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
            SUM((data->>'calories')::float)::int AS kcal,
            SUM((data->>'distance_meters')::float)::int AS dist_m,
            SUM((data->>'duration_seconds')::float)::int AS dur_sec,
            (array_agg(data->>'activity_type' ORDER BY recorded_at DESC))[1] AS workout_type
        FROM health_logs
        WHERE user_id = $1 AND agent = 'workout' AND type = 'activity'
          AND recorded_at >= $2 AND recorded_at < $3
        """,
        user_id, day_start, day_end,
    )
    metrics: dict = {}
    if row and row["dur_sec"]:
        metrics["duration_min"] = round((row["dur_sec"] or 0) / 60)
        metrics["distance_km"] = round((row["dist_m"] or 0) / 1000, 2)
        metrics["kcal"] = row["kcal"] or 0
        if row["workout_type"]:
            metrics["workout_type"] = row["workout_type"]

    return {
        "agent": "workout",
        "insight": _workout_insight(history, metrics),
        "metrics": metrics,
        "history": history,
    }


async def _nutrition_detail(user_id: UUID) -> dict:
    from .db import fetch_nutrition_history
    from .db import get_pool

    history = await fetch_nutrition_history(user_id, days=7)

    day_start, day_end = _nutrition_day_bounds()
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
            ROUND(SUM((data->'totals'->>'protein_g')::float)::numeric) AS protein_g,
            ROUND(SUM((data->'totals'->>'carbs_g')::float)::numeric) AS carbs_g,
            ROUND(SUM((data->'totals'->>'fat_g')::float)::numeric) AS fat_g,
            ROUND(SUM((data->'totals'->>'kcal')::float)::numeric) AS kcal
        FROM health_logs
        WHERE user_id = $1 AND agent = 'nutrition' AND type = 'meal'
          AND recorded_at >= $2 AND recorded_at < $3
        """,
        user_id, day_start, day_end,
    )
    metrics: dict = {}
    if row and row["kcal"] is not None:
        metrics["protein_g"] = int(row["protein_g"] or 0)
        metrics["carbs_g"] = int(row["carbs_g"] or 0)
        metrics["fat_g"] = int(row["fat_g"] or 0)
        metrics["kcal"] = int(row["kcal"] or 0)

    meal_rows = await pool.fetch(
        """
        SELECT recorded_at, data
        FROM health_logs
        WHERE user_id = $1 AND agent = 'nutrition' AND type = 'meal'
          AND source = 'yazio'
          AND recorded_at >= $2 AND recorded_at < $3
        ORDER BY recorded_at ASC
        """,
        user_id, day_start, day_end,
    )
    meals = [_format_nutrition_meal(dict(r)) for r in meal_rows]

    # Body profile for goals
    try:
        from .db import get_body_profile
        profile = await get_body_profile(user_id)
        if profile.get("tdee"):
            metrics["goal_kcal"] = int(profile["tdee"])
        if profile.get("protein_goal_g"):
            metrics["protein_goal_g"] = int(profile["protein_goal_g"])
    except Exception:
        pass

    return {
        "agent": "nutrition",
        "insight": _nutrition_insight(history, metrics),
        "metrics": metrics,
        "history": history,
        "meals": meals,
    }


async def _mood_detail(user_id: UUID) -> dict:
    from .db import fetch_mood_history
    from .db import get_pool
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta
    import json

    history = await fetch_mood_history(user_id, days=7)

    kyiv = ZoneInfo("Europe/Kyiv")
    now_kyiv = datetime.now(kyiv)
    day_start = datetime(now_kyiv.year, now_kyiv.month, now_kyiv.day, tzinfo=kyiv) - timedelta(days=1)
    day_end = day_start + timedelta(days=1)
    pool = await get_pool()
    row = await pool.fetchrow(
        """
        SELECT
            ROUND(AVG((data->>'mood_score')::float)::numeric, 1) AS score,
            ROUND(AVG((data->>'energy')::float)::numeric, 1) AS energy,
            ROUND(AVG((data->>'stress')::float)::numeric, 1) AS stress,
            (array_agg(data->>'valence' ORDER BY recorded_at DESC))[1] AS valence,
            (array_agg(data->'tags' ORDER BY recorded_at DESC))[1] AS tags
        FROM health_logs
        WHERE user_id = $1 AND agent = 'mood' AND type = 'mood'
          AND recorded_at >= $2 AND recorded_at < $3
        """,
        user_id, day_start, day_end,
    )
    metrics: dict = {}
    if row and row["score"] is not None:
        metrics["score"] = float(row["score"])
        if row["energy"] is not None:
            metrics["energy"] = float(row["energy"])
        if row["stress"] is not None:
            metrics["stress"] = float(row["stress"])
        if row["valence"]:
            metrics["valence"] = row["valence"]
        raw_tags = row["tags"]
        if isinstance(raw_tags, str):
            try:
                raw_tags = json.loads(raw_tags)
            except Exception:
                raw_tags = []
        if raw_tags:
            metrics["top_tag"] = raw_tags[0]

    return {
        "agent": "mood",
        "insight": _mood_insight(history, metrics),
        "metrics": metrics,
        "history": history,
    }


async def _habits_detail(user_id: UUID) -> dict:
    from .db import fetch_habits_history
    from shared.db import fetch_active_habits, fetch_habit_logs
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta

    history = await fetch_habits_history(user_id, days=30)

    kyiv = ZoneInfo("Europe/Kyiv")
    today = datetime.now(kyiv).date()
    habit_defs = await fetch_active_habits(user_id)
    logs = await fetch_habit_logs(user_id, days=7)

    completed_days = set()
    for r in logs:
        d = r["recorded_at"].astimezone(kyiv).date()
        if (r.get("data") or {}).get("completed"):
            completed_days.add(d.isoformat())

    # Simple streak: consecutive days from today backward with any completion
    streak = 0
    cursor = today
    for _ in range(60):
        if cursor.isoformat() in completed_days:
            streak += 1
            cursor = cursor - timedelta(days=1)
        else:
            break

    completion_7d = len([d for d in completed_days
                         if (today - timedelta(days=6)).isoformat() <= d <= today.isoformat()]) / 7.0

    # Missed yesterday
    yesterday = (today - timedelta(days=1)).isoformat()
    missed_logs = {(r.get("data") or {}).get("habit_id") for r in logs
                   if r["recorded_at"].astimezone(kyiv).date().isoformat() == yesterday
                   and (r.get("data") or {}).get("completed")}
    missed_names = [h["name"] for h in habit_defs if h["id"] not in missed_logs][:3]

    metrics = {
        "streak": streak,
        "completion_7d": round(completion_7d, 2),
        "active_count": len(habit_defs),
        "missed_names": missed_names,
    }

    return {
        "agent": "habits",
        "insight": _habits_insight(history, metrics),
        "metrics": metrics,
        "history": history,
    }


async def _recovery_detail(user_id: UUID) -> dict:
    from .db import fetch_recovery_history
    from .recovery_context import fetch_recovery_shape
    from zoneinfo import ZoneInfo
    from datetime import datetime

    history = await fetch_recovery_history(user_id, days=7)

    kyiv = ZoneInfo("Europe/Kyiv")
    today = datetime.now(kyiv).date()
    shape = await fetch_recovery_shape(user_id, today)

    metrics: dict = {}
    if shape:
        metrics["bucket"] = shape.get("bucket", "unknown")
        for item in shape.get("top3") or []:
            key = item.get("key")
            val = item.get("value")
            delta = item.get("delta_pct")
            if key and val is not None:
                metrics[key] = round(val, 1)
                if delta is not None:
                    metrics[f"{key}_delta_pct"] = round(delta, 1)
    else:
        metrics["bucket"] = "unknown"

    return {
        "agent": "recovery",
        "insight": _recovery_insight(history, metrics),
        "metrics": metrics,
        "history": history,
    }


async def _medication_detail(user_id: UUID) -> dict:
    from .db import fetch_medication_history
    from shared.db import fetch_active_medications, fetch_medication_logs
    from zoneinfo import ZoneInfo
    from datetime import datetime, timedelta

    history = await fetch_medication_history(user_id, days=30)

    meds = await fetch_active_medications(user_id)
    logs_7d = await fetch_medication_logs(user_id, days=7)

    kyiv = ZoneInfo("Europe/Kyiv")
    today = datetime.now(kyiv).date()
    taken_days = {r["recorded_at"].astimezone(kyiv).date().isoformat() for r in logs_7d}
    adherence_7d = len([
        d for d in [
            (today - timedelta(days=i)).isoformat() for i in range(7)
        ] if d in taken_days
    ]) / 7.0

    taken_names_2d = {(r.get("data") or {}).get("name") for r in logs_7d
                      if r["recorded_at"].astimezone(kyiv).date() >= today - timedelta(days=2)}
    missed_names = [m["name"] for m in meds if m["name"] not in taken_names_2d]

    metrics = {
        "adherence_7d": round(adherence_7d, 2),
        "active_count": len(meds),
        "missed_names": missed_names,
    }

    return {
        "agent": "medication",
        "insight": _medication_insight(history, metrics),
        "metrics": metrics,
        "history": history,
    }


async def _finance_detail(user_id: UUID) -> dict:
    from .db import fetch_finance_history
    from .finance_queries import spending_by_category, runway

    history = await fetch_finance_history(user_id, days=7)

    spent_week = round(sum(h["value"] for h in history), 2)

    top_category = ""
    try:
        from datetime import datetime
        from zoneinfo import ZoneInfo
        month_str = datetime.now(ZoneInfo("Europe/Kyiv")).strftime("%Y-%m")
        categories = await spending_by_category(user_id, month_str)
        if categories:
            top_category = categories[0][0] if categories else ""
    except Exception:
        pass

    runway_days: int | None = None
    try:
        rw = await runway(user_id)
        if rw:
            first_currency = next(iter(rw.values()), {})
            runway_days = int(first_currency.get("days", 0)) or None
    except Exception:
        pass

    metrics: dict = {
        "spent_week": spent_week,
    }
    if top_category:
        metrics["top_category"] = top_category
    if runway_days:
        metrics["runway_days"] = runway_days

    return {
        "agent": "finance",
        "insight": _finance_insight(history, metrics),
        "metrics": metrics,
        "history": history,
    }


async def _calendar_detail(user_id: UUID) -> dict:
    from datetime import date
    from .calendar_context import fetch_calendar_events, fetch_calendar_shape, _parse_iso_local

    today = date.today()
    events_raw = await fetch_calendar_events(user_id, today, max_results=20)
    events = [e for ev in events_raw if (e := _format_calendar_event(ev))]
    busy_minutes = 0
    for ev in events_raw:
        if ev.get("all_day"):
            continue
        start = _parse_iso_local(ev.get("start", ""))
        end = _parse_iso_local(ev.get("end", ""))
        if start is not None and end is not None:
            busy_minutes += max(0, int((end - start).total_seconds() // 60))

    shape = await fetch_calendar_shape(today, user_id) or {}
    metrics = {
        "events_count": len(events),
        "busy_minutes": busy_minutes,
        "events": events[:10],
        "first_free_slot_start": shape.get("first_free_slot_start"),
        "first_free_slot_len_min": shape.get("first_free_slot_len_min"),
    }
    return {
        "agent": "calendar",
        "insight": _calendar_insight(metrics),
        "metrics": metrics,
        "history": [],
    }


# ── Dispatcher ────────────────────────────────────────────────────────────────

_BUILDERS = {
    "sleep":      _sleep_detail,
    "workout":    _workout_detail,
    "nutrition":  _nutrition_detail,
    "mood":       _mood_detail,
    "habits":     _habits_detail,
    "recovery":   _recovery_detail,
    "medication": _medication_detail,
    "finance":    _finance_detail,
    "calendar":   _calendar_detail,
}


async def get_agent_detail(agent_id: str, user_id: UUID) -> dict:
    """Public entry point. Returns AgentDetail dict."""
    builder = _BUILDERS.get(agent_id)
    if builder is None:
        raise ValueError(f"Unknown agent_id: {agent_id}")
    try:
        return await builder(user_id)
    except Exception as e:
        logger.warning("agent_detail builder failed for %s: %s", agent_id, e)
        return {"agent": agent_id, "insight": "", "metrics": {}, "history": []}
