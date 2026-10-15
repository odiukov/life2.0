import asyncpg
import json
import os
from datetime import datetime, timezone, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.db import (
    fetch_active_habits,
    fetch_habit_logs,
    fetch_active_medications,
    fetch_medication_logs,
    fetch_body_logs,
)

_pool: asyncpg.Pool | None = None


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"], init=_set_json_codec)
    return _pool


def _describe_log(row: dict) -> str:
    """Human-readable description of a health_logs row for the activity feed."""
    data = row["data"] or {}
    t = row["type"]
    if t == "sleep_session":
        hours = round(data.get("duration_seconds", 0) / 3600, 1)
        score = data.get("score")
        score_str = f", score {score}" if score else ""
        return f"slept {hours}h{score_str}"
    if t == "activity":
        kind = data.get("activity_type", "workout")
        mins = round(data.get("duration_seconds", 0) / 60)
        name = data.get("name", "")
        return f"{name or kind} {mins} min"
    if t == "daily_stats":
        steps = data.get("steps", 0)
        return f"{steps:,} steps"
    return t


async def get_stats(user_id: UUID) -> dict:
    """Return per-agent record counts (this week vs prev week) combining health_logs
    (Garmin) and tasks (manual chat entries), plus last 10 records as activity feed."""
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    agent_type_map = {
        "sleep": ["sleep_session"],
        "workout": ["activity"],
        "nutrition": ["meal"],
    }
    agent_stats = {}
    # Build list of 7 day-start timestamps: oldest first (6 days ago → today)
    day_starts = [
        (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(6, -1, -1)
    ]

    for agent, types in agent_type_map.items():
        row = await pool.fetchrow(
            """
            SELECT
                COUNT(*) FILTER (WHERE ts >= $4) AS this_week,
                COUNT(*) FILTER (WHERE ts >= $5 AND ts < $4) AS prev_week
            FROM (
                SELECT recorded_at AS ts FROM health_logs
                WHERE user_id=$1 AND agent=$2 AND type=ANY($3) AND recorded_at >= $5
                UNION ALL
                SELECT created_at AS ts FROM tasks
                WHERE agent=$2 AND created_at >= $5
            ) combined
            """,
            user_id,
            agent,
            types,
            week_ago,
            two_weeks_ago,
        )
        tw = int(row["this_week"]) if row else 0
        pw = int(row["prev_week"]) if row else 0

        # Per-day counts for the last 7 days
        daily_rows = await pool.fetch(
            """
            SELECT date_trunc('day', ts AT TIME ZONE 'UTC')::date AS day, COUNT(*) AS cnt
            FROM (
                SELECT recorded_at AS ts FROM health_logs
                WHERE user_id=$1 AND agent=$2 AND type=ANY($3) AND recorded_at >= $4
                UNION ALL
                SELECT created_at AS ts FROM tasks
                WHERE agent=$2 AND created_at >= $4
            ) combined
            GROUP BY day
            """,
            user_id,
            agent,
            types,
            day_starts[0],
        )
        daily_map = {r["day"]: int(r["cnt"]) for r in daily_rows}
        daily = [daily_map.get(d.date(), 0) for d in day_starts]

        agent_stats[agent] = {
            "tasks_week": tw,
            "tasks_prev_week": pw,
            "delta": tw - pw,
            "daily": daily,
        }

    health_rows = await pool.fetch(
        "SELECT agent, type, data, recorded_at AS ts FROM health_logs "
        "WHERE user_id = $1 ORDER BY recorded_at DESC LIMIT 20",
        user_id,
    )
    task_rows = await pool.fetch(
        "SELECT agent, skill_id AS type, input, created_at AS ts FROM tasks ORDER BY created_at DESC LIMIT 20"
    )

    combined = []
    for r in health_rows:
        combined.append(
            {
                "agent": r["agent"],
                "task_type": r["type"],
                "message": _describe_log({"type": r["type"], "data": r["data"]}),
                "created_at": r["ts"].isoformat(),
            }
        )
    for r in task_rows:
        combined.append(
            {
                "agent": r["agent"],
                "task_type": r["type"],
                "message": ((r["input"] or {}).get("message", "") or "")[:80],
                "created_at": r["ts"].isoformat(),
            }
        )

    combined.sort(key=lambda x: x["created_at"], reverse=True)
    activity = combined[:10]

    return {"agents": agent_stats, "activity": activity}


async def get_health_summary(user_id: UUID) -> dict:
    """Return personal health metrics: body composition, last sleep, daily stats, weekly trends, last recommendation."""
    pool = await get_pool()
    now = datetime.now(timezone.utc)

    # Build list of 7 day-start timestamps: oldest first (6 days ago → today)
    day_starts = [
        (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(6, -1, -1)
    ]

    # Latest body composition
    body_row = await pool.fetchrow(
        "SELECT data, recorded_at FROM health_logs "
        "WHERE user_id = $1 AND type='body_composition' ORDER BY recorded_at DESC LIMIT 1",
        user_id,
    )
    body = None
    if body_row:
        d = body_row["data"] or {}
        body = {
            "weight_kg": d.get("weight_kg"),
            "body_fat_pct": d.get("body_fat_pct"),
            "lean_mass_kg": d.get("lean_mass_kg"),
            "bmi": d.get("bmi"),
            "recorded_at": body_row["recorded_at"].isoformat(),
        }

    # Last sleep session
    sleep_row = await pool.fetchrow(
        "SELECT data, recorded_at FROM health_logs "
        "WHERE user_id = $1 AND agent='sleep' AND type='sleep_session' ORDER BY recorded_at DESC LIMIT 1",
        user_id,
    )
    sleep = None
    if sleep_row:
        d = sleep_row["data"] or {}
        # Prefer hrv_status.hrv_rmssd (matches the Garmin watch widget) over
        # sleep_session.hrv_weekly_avg (sleep-DTO average; computed differently).
        hrv_row = await pool.fetchrow(
            "SELECT (data->>'hrv_rmssd')::float AS hrv_rmssd FROM health_logs "
            "WHERE user_id = $1 AND agent='sleep' AND type='hrv_status' "
            "  AND recorded_at >= NOW() - INTERVAL '3 days' "
            "ORDER BY recorded_at DESC LIMIT 1",
            user_id,
        )
        hrv = (
            int(hrv_row["hrv_rmssd"])
            if hrv_row and hrv_row["hrv_rmssd"]
            else d.get("hrv_weekly_avg")
        )
        sleep = {
            "duration_hours": round(d.get("duration_seconds", 0) / 3600, 1),
            "score": d.get("score"),
            "hrv": hrv,
            "deep_hours": round(d.get("deep_sleep_seconds", 0) / 3600, 1),
            "rem_hours": round(d.get("rem_sleep_seconds", 0) / 3600, 1),
            "light_hours": round(d.get("light_sleep_seconds", 0) / 3600, 1),
            "recorded_at": sleep_row["recorded_at"].isoformat(),
        }

    # Latest daily stats
    daily_row = await pool.fetchrow(
        "SELECT data, recorded_at FROM health_logs "
        "WHERE user_id = $1 AND type='daily_stats' ORDER BY recorded_at DESC LIMIT 1",
        user_id,
    )
    daily = None
    if daily_row:
        d = daily_row["data"] or {}
        daily = {
            "steps": d.get("steps"),
            "calories_active": d.get("calories_active"),
            "body_battery_max": d.get("body_battery_max"),
            "resting_hr": d.get("resting_hr"),
            "stress_avg": d.get("stress_avg"),
            "recorded_at": daily_row["recorded_at"].isoformat(),
        }

    # Last 7 days sleep hours/day
    sleep_daily = await pool.fetch(
        """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           AVG((data->>'duration_seconds')::float / 3600) AS hours
           FROM health_logs WHERE user_id = $1 AND agent='sleep' AND type='sleep_session' AND recorded_at >= $2
           GROUP BY day""",
        user_id,
        day_starts[0],
    )
    sleep_map = {r["day"]: round(float(r["hours"]), 1) for r in sleep_daily}
    sleep_hours = [sleep_map.get(d.date(), 0) for d in day_starts]

    # Last 7 days workout minutes/day
    workout_daily = await pool.fetch(
        """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           SUM((data->>'duration_seconds')::float / 60) AS minutes
           FROM health_logs WHERE user_id = $1 AND agent='workout' AND type='activity' AND recorded_at >= $2
           GROUP BY day""",
        user_id,
        day_starts[0],
    )
    workout_map = {r["day"]: round(float(r["minutes"])) for r in workout_daily}
    workout_minutes = [workout_map.get(d.date(), 0) for d in day_starts]

    # Last 7 days nutrition calories/day (meal rows inserted by Yazio sync)
    nutrition_daily = await pool.fetch(
        """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           SUM((data->'totals'->>'kcal')::float) AS calories
           FROM health_logs WHERE user_id = $1 AND agent='nutrition' AND type='meal' AND recorded_at >= $2
           GROUP BY day""",
        user_id,
        day_starts[0],
    )
    nutrition_map = {r["day"]: round(float(r["calories"])) for r in nutrition_daily}
    nutrition_calories = [nutrition_map.get(d.date(), 0) for d in day_starts]

    # Last recommendation from tasks (tasks not yet user-scoped)
    rec_row = await pool.fetchrow(
        "SELECT agent, skill_id, output, created_at FROM tasks WHERE output IS NOT NULL AND output != '' ORDER BY created_at DESC LIMIT 1"
    )
    recommendation = None
    if rec_row and rec_row["output"]:
        recommendation = {
            "agent": rec_row["agent"],
            "text": rec_row["output"][:400],
            "created_at": rec_row["created_at"].isoformat(),
        }

    return {
        "body": body,
        "sleep": sleep,
        "daily": daily,
        "trends": {
            "sleep_hours": sleep_hours,
            "workout_minutes": workout_minutes,
            "nutrition_calories": nutrition_calories,
        },
        "recommendation": recommendation,
    }


async def clear_activity() -> int:
    """Delete all tasks from the activity feed. Returns number of deleted rows."""
    pool = await get_pool()
    result = await pool.execute("DELETE FROM tasks")
    # result is like "DELETE 12"
    return int(result.split()[-1])


async def get_body_profile(user_id) -> dict:
    """Return body_profile sub-dict from users.preferences, or {}."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT preferences FROM users WHERE id = $1",
        user_id,
    )
    if not row:
        return {}
    prefs = row["preferences"] or {}
    return prefs.get("body_profile") or {}


async def save_body_profile(user_id, updates: dict) -> None:
    """Merge `updates` into users.preferences['body_profile']."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT preferences FROM users WHERE id = $1",
        user_id,
    )
    prefs = dict(row["preferences"] or {}) if row else {}
    profile = dict(prefs.get("body_profile") or {})
    for k, v in updates.items():
        if v is not None:
            profile[k] = v
        elif k in profile:
            del profile[k]
    prefs["body_profile"] = profile
    await pool.execute(
        "UPDATE users SET preferences = $1 WHERE id = $2",
        prefs,
        user_id,
    )


async def insert_body_rows(rows: list[dict], user_id) -> tuple[int, int]:
    """Upsert body_composition rows from ViHealth PDF into health_logs."""
    if not rows:
        return 0, 0
    pool = await get_pool()
    written = 0
    unchanged = 0
    async with pool.acquire() as conn:
        for row in rows:
            result = await conn.execute(
                """
                INSERT INTO health_logs (agent, type, data, recorded_at, source, user_id)
                VALUES ($1, $2, $3, $4, $5, $6)
                ON CONFLICT (user_id, source, type, recorded_at) DO UPDATE
                  SET data = EXCLUDED.data
                  WHERE health_logs.data IS DISTINCT FROM EXCLUDED.data
                """,
                row["agent"],
                row["type"],
                row["data"],
                row["recorded_at"],
                row["source"],
                user_id,
            )
            if result.endswith("1"):
                written += 1
            else:
                unchanged += 1
    return written, unchanged


async def fetch_sleep_history(user_id: UUID, days: int = 7) -> list[dict]:
    """Return `days` daily sleep entries (hours), ascending by date. Missing days → value 0."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        WITH dates AS (
            SELECT generate_series(
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date - ($2 - 1),
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date,
                '1 day'::interval
            )::date AS d
        ),
        raw AS (
            SELECT
                (recorded_at AT TIME ZONE 'Europe/Kyiv')::date AS d,
                MAX((data->>'duration_seconds')::int) AS dur_sec  -- one session per night; MAX picks the primary
            FROM health_logs
            WHERE user_id = $1 AND agent = 'sleep' AND type = 'sleep_session'
              AND recorded_at >= NOW() - make_interval(days => $2 + 2)
            GROUP BY 1
        )
        SELECT dates.d::text AS date,
               COALESCE(ROUND((raw.dur_sec / 3600.0)::numeric, 2)::float, 0.0) AS value
        FROM dates
        LEFT JOIN raw ON raw.d = dates.d
        ORDER BY dates.d
        """,
        user_id,
        days,
    )
    result = []
    for r in rows:
        if r["value"] == 0.0:
            result.append({"date": r["date"], "value": 0.0, "label": "—"})
            continue
        h = r["value"]
        hrs = int(h)
        mins = round((h - hrs) * 60)
        label = f"{hrs}h {mins}m" if mins else f"{hrs}h"
        result.append({"date": r["date"], "value": float(r["value"]), "label": label})
    return result


async def fetch_workout_history(user_id: UUID, days: int = 7) -> list[dict]:
    """Return `days` daily workout duration minutes, ascending by date. Missing days → value 0."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        WITH dates AS (
            SELECT generate_series(
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date - ($2 - 1),
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date,
                '1 day'::interval
            )::date AS d
        ),
        raw AS (
            SELECT
                (recorded_at AT TIME ZONE 'Europe/Kyiv')::date AS d,
                SUM(COALESCE((data->>'duration_seconds')::float, 0)) / 60.0 AS minutes  -- non-distance activities (strength, MMA) still count
            FROM health_logs
            WHERE user_id = $1 AND agent = 'workout' AND type = 'activity'
              AND recorded_at >= NOW() - make_interval(days => $2 + 2)
            GROUP BY 1
        )
        SELECT dates.d::text AS date,
               COALESCE(ROUND(raw.minutes)::int, 0) AS value
        FROM dates
        LEFT JOIN raw ON raw.d = dates.d
        ORDER BY dates.d
        """,
        user_id,
        days,
    )
    return [
        {
            "date": r["date"],
            "value": float(r["value"]),
            "label": f"{int(r['value'])} min" if r["value"] > 0 else "—",
        }
        for r in rows
    ]


async def fetch_nutrition_history(user_id: UUID, days: int = 7) -> list[dict]:
    """Return `days` daily kcal totals, ascending by date. Missing days → value 0."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        WITH dates AS (
            SELECT generate_series(
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date - ($2 - 1),
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date,
                '1 day'::interval
            )::date AS d
        ),
        raw AS (
            SELECT
                (recorded_at AT TIME ZONE 'Europe/Kyiv')::date AS d,
                ROUND(SUM((data->'totals'->>'kcal')::float)::numeric)::int AS kcal
            FROM health_logs
            WHERE user_id = $1 AND agent = 'nutrition' AND type = 'meal'
              AND recorded_at >= NOW() - make_interval(days => $2 + 2)
            GROUP BY 1
        )
        SELECT dates.d::text AS date,
               COALESCE(raw.kcal::float, 0.0) AS value
        FROM dates
        LEFT JOIN raw ON raw.d = dates.d
        ORDER BY dates.d
        """,
        user_id,
        days,
    )
    return [
        {
            "date": r["date"],
            "value": float(r["value"]),
            "label": f"{int(r['value'])} kcal" if r["value"] > 0 else "—",
        }
        for r in rows
    ]


async def fetch_mood_history(user_id: UUID, days: int = 7) -> list[dict]:
    """Return `days` daily avg mood score, ascending by date. Missing days → value 0."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        WITH dates AS (
            SELECT generate_series(
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date - ($2 - 1),
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date,
                '1 day'::interval
            )::date AS d
        ),
        raw AS (
            SELECT
                (recorded_at AT TIME ZONE 'Europe/Kyiv')::date AS d,
                ROUND(AVG((data->>'mood_score')::float)::numeric, 1)::float AS score
            FROM health_logs
            WHERE user_id = $1 AND type = 'mood'
              AND recorded_at >= NOW() - make_interval(days => $2 + 2)
            GROUP BY 1
        )
        SELECT dates.d::text AS date,
               COALESCE(raw.score, 0.0) AS value
        FROM dates
        LEFT JOIN raw ON raw.d = dates.d
        ORDER BY dates.d
        """,
        user_id,
        days,
    )
    return [
        {
            "date": r["date"],
            "value": float(r["value"]),
            "label": f"{r['value']:.1f}" if r["value"] > 0 else "—",
        }
        for r in rows
    ]


async def fetch_recovery_history(user_id: UUID, days: int = 7) -> list[dict]:
    """Return `days` daily HRV values, ascending by date. Missing days → value 0."""
    from shared.db import fetch_recovery_metrics

    kyiv = ZoneInfo("Europe/Kyiv")
    today = datetime.now(kyiv).date()
    metrics = await fetch_recovery_metrics(user_id, days=days + 2)

    result = []
    for i in range(days - 1, -1, -1):
        d = today - timedelta(days=i)
        key = d.isoformat()
        day_data = metrics.get(key) or {}
        hrv = day_data.get("hrv") or 0.0
        result.append(
            {
                "date": key,
                "value": float(hrv),
                "label": f"{int(hrv)} ms" if hrv else "—",
            }
        )
    return result


async def fetch_habits_history(user_id: UUID, days: int = 30) -> list[dict]:
    """Return `days` daily habit completion flag, ascending by date. value=1 if any completed."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        WITH dates AS (
            SELECT generate_series(
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date - ($2 - 1),
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date,
                '1 day'::interval
            )::date AS d
        ),
        raw AS (
            SELECT
                (recorded_at AT TIME ZONE 'Europe/Kyiv')::date AS d,
                BOOL_OR(COALESCE((data->>'completed')::boolean, false)) AS any_done
            FROM health_logs
            WHERE user_id = $1 AND type = 'habit'
              AND recorded_at >= NOW() - make_interval(days => $2 + 2)
            GROUP BY 1
        )
        SELECT dates.d::text AS date,
               CASE WHEN raw.any_done THEN 1.0 ELSE 0.0 END AS value
        FROM dates
        LEFT JOIN raw ON raw.d = dates.d
        ORDER BY dates.d
        """,
        user_id,
        days,
    )
    return [
        {"date": r["date"], "value": float(r["value"]), "label": "✅" if r["value"] else "⬜"}
        for r in rows
    ]


async def fetch_medication_history(user_id: UUID, days: int = 30) -> list[dict]:
    """Return `days` daily medication-taken flag, ascending by date. value=1 if any taken."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        WITH dates AS (
            SELECT generate_series(
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date - ($2 - 1),
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date,
                '1 day'::interval
            )::date AS d
        ),
        raw AS (
            SELECT DISTINCT
                (recorded_at AT TIME ZONE 'Europe/Kyiv')::date AS d
            FROM health_logs
            WHERE user_id = $1 AND type = 'medication_taken'
              AND recorded_at >= NOW() - make_interval(days => $2 + 2)
        )
        SELECT dates.d::text AS date,
               CASE WHEN raw.d IS NOT NULL THEN 1.0 ELSE 0.0 END AS value
        FROM dates
        LEFT JOIN raw ON raw.d = dates.d
        ORDER BY dates.d
        """,
        user_id,
        days,
    )
    return [
        {"date": r["date"], "value": float(r["value"]), "label": "✅" if r["value"] else "⬜"}
        for r in rows
    ]


async def fetch_finance_history(user_id: UUID, days: int = 7) -> list[dict]:
    """Return `days` daily OUT spend in primary currency, ascending by date. Missing days → 0."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        WITH primary_cur AS (
            SELECT currency FROM finance_transactions
            WHERE user_id = $1
            GROUP BY currency ORDER BY COUNT(*) DESC LIMIT 1
        ),
        dates AS (
            SELECT generate_series(
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date - ($2 - 1),
                (NOW() AT TIME ZONE 'Europe/Kyiv')::date,
                '1 day'::interval
            )::date AS d
        ),
        raw AS (
            SELECT
                (ts AT TIME ZONE 'Europe/Kyiv')::date AS d,
                SUM(amount)::float AS total
            FROM finance_transactions
            WHERE user_id = $1 AND direction = 'OUT'
              AND currency = (SELECT currency FROM primary_cur)
              AND ts >= NOW() - make_interval(days => $2 + 2)
            GROUP BY 1
        )
        SELECT dates.d::text AS date,
               COALESCE(ROUND(raw.total::numeric, 2)::float, 0.0) AS value
        FROM dates
        LEFT JOIN raw ON raw.d = dates.d
        ORDER BY dates.d
        """,
        user_id,
        days,
    )
    return [
        {
            "date": r["date"],
            "value": float(r["value"]),
            "label": f"${r['value']:.0f}" if r["value"] > 0 else "—",
        }
        for r in rows
    ]
