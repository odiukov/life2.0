import asyncpg
import json
import os
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

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


async def get_stats() -> dict:
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
                COUNT(*) FILTER (WHERE ts >= $3) AS this_week,
                COUNT(*) FILTER (WHERE ts >= $4 AND ts < $3) AS prev_week
            FROM (
                SELECT recorded_at AS ts FROM health_logs
                WHERE agent=$1 AND type=ANY($2) AND recorded_at >= $4
                UNION ALL
                SELECT created_at AS ts FROM tasks
                WHERE agent=$1 AND created_at >= $4
            ) combined
            """,
            agent, types, week_ago, two_weeks_ago
        )
        tw = int(row["this_week"]) if row else 0
        pw = int(row["prev_week"]) if row else 0

        # Per-day counts for the last 7 days
        daily_rows = await pool.fetch(
            """
            SELECT date_trunc('day', ts AT TIME ZONE 'UTC')::date AS day, COUNT(*) AS cnt
            FROM (
                SELECT recorded_at AS ts FROM health_logs
                WHERE agent=$1 AND type=ANY($2) AND recorded_at >= $3
                UNION ALL
                SELECT created_at AS ts FROM tasks
                WHERE agent=$1 AND created_at >= $3
            ) combined
            GROUP BY day
            """,
            agent, types, day_starts[0]
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
        "SELECT agent, type, data, recorded_at AS ts FROM health_logs ORDER BY recorded_at DESC LIMIT 20"
    )
    task_rows = await pool.fetch(
        "SELECT agent, skill_id AS type, input, created_at AS ts FROM tasks ORDER BY created_at DESC LIMIT 20"
    )

    combined = []
    for r in health_rows:
        combined.append({
            "agent": r["agent"],
            "task_type": r["type"],
            "message": _describe_log({"type": r["type"], "data": r["data"]}),
            "created_at": r["ts"].isoformat(),
        })
    for r in task_rows:
        combined.append({
            "agent": r["agent"],
            "task_type": r["type"],
            "message": ((r["input"] or {}).get("message", "") or "")[:80],
            "created_at": r["ts"].isoformat(),
        })

    combined.sort(key=lambda x: x["created_at"], reverse=True)
    activity = combined[:10]

    return {"agents": agent_stats, "activity": activity}


async def get_health_summary() -> dict:
    """Return personal health metrics: body composition, last sleep, daily stats, weekly trends, last recommendation."""
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)

    # Build list of 7 day-start timestamps: oldest first (6 days ago → today)
    day_starts = [
        (now - timedelta(days=i)).replace(hour=0, minute=0, second=0, microsecond=0)
        for i in range(6, -1, -1)
    ]

    # Latest body composition
    body_row = await pool.fetchrow(
        "SELECT data, recorded_at FROM health_logs WHERE type='body_composition' ORDER BY recorded_at DESC LIMIT 1"
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
        "SELECT data, recorded_at FROM health_logs WHERE agent='sleep' AND type='sleep_session' ORDER BY recorded_at DESC LIMIT 1"
    )
    sleep = None
    if sleep_row:
        d = sleep_row["data"] or {}
        sleep = {
            "duration_hours": round(d.get("duration_seconds", 0) / 3600, 1),
            "score": d.get("score"),
            "hrv": d.get("hrv_weekly_avg"),
            "deep_hours": round(d.get("deep_sleep_seconds", 0) / 3600, 1),
            "rem_hours": round(d.get("rem_sleep_seconds", 0) / 3600, 1),
            "light_hours": round(d.get("light_sleep_seconds", 0) / 3600, 1),
            "recorded_at": sleep_row["recorded_at"].isoformat(),
        }

    # Latest daily stats
    daily_row = await pool.fetchrow(
        "SELECT data, recorded_at FROM health_logs WHERE type='daily_stats' ORDER BY recorded_at DESC LIMIT 1"
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
           FROM health_logs WHERE agent='sleep' AND type='sleep_session' AND recorded_at >= $1
           GROUP BY day""",
        day_starts[0]
    )
    sleep_map = {r["day"]: round(float(r["hours"]), 1) for r in sleep_daily}
    sleep_hours = [sleep_map.get(d.date(), 0) for d in day_starts]

    # Last 7 days workout minutes/day
    workout_daily = await pool.fetch(
        """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           SUM((data->>'duration_seconds')::float / 60) AS minutes
           FROM health_logs WHERE agent='workout' AND type='activity' AND recorded_at >= $1
           GROUP BY day""",
        day_starts[0]
    )
    workout_map = {r["day"]: round(float(r["minutes"])) for r in workout_daily}
    workout_minutes = [workout_map.get(d.date(), 0) for d in day_starts]

    # Last 7 days nutrition calories/day (meal rows inserted by Yazio sync)
    nutrition_daily = await pool.fetch(
        """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           SUM((data->'totals'->>'kcal')::float) AS calories
           FROM health_logs WHERE agent='nutrition' AND type='meal' AND recorded_at >= $1
           GROUP BY day""",
        day_starts[0]
    )
    nutrition_map = {r["day"]: round(float(r["calories"])) for r in nutrition_daily}
    nutrition_calories = [nutrition_map.get(d.date(), 0) for d in day_starts]

    # Last recommendation from tasks
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


async def get_tasks_today(agent: str) -> int:
    """Count tasks for an agent since midnight UTC today."""
    pool = await get_pool()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2",
        agent, today_start
    )
    return int(row["cnt"]) if row else 0


async def get_yesterday_metrics(use_today: bool = False) -> dict:
    """Return yesterday's health metrics aggregated by domain (Europe/Kyiv timezone).

    Returns a dict with keys: date (str), sleep (dict|None), workout (dict|None), nutrition (dict|None).
    """
    kyiv = ZoneInfo("Europe/Kyiv")
    now_kyiv = datetime.now(kyiv)
    target = now_kyiv.date() if use_today else now_kyiv.date() - timedelta(days=1)
    yesterday = target
    day_start = datetime(yesterday.year, yesterday.month, yesterday.day, tzinfo=kyiv)
    day_end = day_start + timedelta(days=1)

    pool = await get_pool()

    # Sleep: take the most recent sleep_session — that's last night, the one the
    # user actually woke from this morning. Filtering by yesterday's start-time
    # window misses it (its recorded_at is yesterday evening UTC = today early
    # morning Kyiv, so it falls outside the [yesterday 00:00 Kyiv, today 00:00
    # Kyiv) range and the brief shows two-nights-ago sleep instead).
    # Cap freshness at ~36h before yesterday's start so we don't surface stale
    # data when Garmin sync has been silent for days.
    sleep_row = await pool.fetchrow(
        """
        SELECT
            (data->>'duration_seconds')::int AS duration_seconds,
            (data->>'deep_sleep_seconds')::int AS deep_sleep_seconds,
            (data->>'hrv_weekly_avg')::float AS hrv_weekly_avg,
            (data->>'score')::int AS score
        FROM health_logs
        WHERE agent = 'sleep' AND type = 'sleep_session'
          AND recorded_at >= $1
        ORDER BY recorded_at DESC
        LIMIT 1
        """,
        day_start - timedelta(hours=12),
    )
    sleep = None
    if sleep_row:
        sleep = {
            "duration_seconds": sleep_row["duration_seconds"] or 0,
            "deep_sleep_seconds": sleep_row["deep_sleep_seconds"] or 0,
            "hrv": int(sleep_row["hrv_weekly_avg"]) if sleep_row["hrv_weekly_avg"] else None,
            "score": sleep_row["score"],
        }

    # Workout: aggregate all activities for yesterday
    workout_row = await pool.fetchrow(
        """
        SELECT
            SUM((data->>'calories')::float)::int AS total_calories,
            SUM((data->>'distance_meters')::float)::int AS total_distance_meters,
            COUNT(*) AS activity_count,
            (array_agg(data->>'name' ORDER BY recorded_at DESC))[1] AS first_name,
            (array_agg(data->>'activity_type' ORDER BY recorded_at DESC))[1] AS first_type
        FROM health_logs
        WHERE agent = 'workout' AND type = 'activity'
          AND recorded_at >= $1 AND recorded_at < $2
        """,
        day_start, day_end,
    )
    workout = None
    if workout_row and workout_row["activity_count"]:
        workout = {
            "total_calories": workout_row["total_calories"] or 0,
            "total_distance_meters": workout_row["total_distance_meters"] or 0,
            "activity_count": int(workout_row["activity_count"]),
            "first_name": workout_row["first_name"] or "",
            "first_type": workout_row["first_type"] or "",
        }

    # Nutrition: sum all meals for yesterday (type='meal' from Yazio)
    nutrition_row = await pool.fetchrow(
        """
        SELECT
            SUM((data->'totals'->>'kcal')::float) AS kcal,
            SUM((data->'totals'->>'protein_g')::float) AS protein_g,
            SUM((data->'totals'->>'carbs_g')::float) AS carbs_g,
            SUM((data->'totals'->>'fat_g')::float) AS fat_g
        FROM health_logs
        WHERE agent = 'nutrition' AND type = 'meal'
          AND recorded_at >= $1 AND recorded_at < $2
        """,
        day_start, day_end,
    )
    nutrition = None
    if nutrition_row and nutrition_row["kcal"] is not None:
        nutrition = {
            "kcal": round(nutrition_row["kcal"] or 0),
            "protein_g": round(nutrition_row["protein_g"] or 0),
            "carbs_g": round(nutrition_row["carbs_g"] or 0),
            "fat_g": round(nutrition_row["fat_g"] or 0),
        }

    # Mood: aggregate all entries for yesterday (Kyiv day)
    mood_row = await pool.fetchrow(
        """
        SELECT
            COUNT(*) AS count,
            AVG((data->>'mood_score')::float) AS avg_score,
            AVG((data->>'stress')::float) AS avg_stress,
            AVG((data->>'energy')::float) AS avg_energy,
            (array_agg(data->>'valence' ORDER BY recorded_at DESC))[1] AS last_valence,
            (array_agg(data->'tags' ORDER BY recorded_at DESC))[1] AS last_tags,
            (array_agg((data->>'mood_score')::float ORDER BY recorded_at ASC))[1] AS first_score,
            (array_agg((data->>'mood_score')::float ORDER BY recorded_at DESC))[1] AS last_score
        FROM health_logs
        WHERE type = 'mood'
          AND recorded_at >= $1 AND recorded_at < $2
        """,
        day_start, day_end,
    )
    mood = None
    if mood_row and mood_row["count"] and int(mood_row["count"]) > 0:
        raw_tags = mood_row["last_tags"]
        if isinstance(raw_tags, str):
            try:
                raw_tags = json.loads(raw_tags)
            except Exception:
                raw_tags = []
        mood = {
            "count": int(mood_row["count"]),
            "avg_score": round(float(mood_row["avg_score"]), 1) if mood_row["avg_score"] is not None else None,
            "avg_stress": round(float(mood_row["avg_stress"]), 1) if mood_row["avg_stress"] is not None else None,
            "avg_energy": round(float(mood_row["avg_energy"]), 1) if mood_row["avg_energy"] is not None else None,
            "last_valence": mood_row["last_valence"],
            "last_tags": raw_tags or [],
            "first_score": int(mood_row["first_score"]) if mood_row["first_score"] is not None else None,
            "last_score": int(mood_row["last_score"]) if mood_row["last_score"] is not None else None,
        }

    return {
        "date": f"{yesterday.strftime('%a')} {yesterday.day} {yesterday.strftime('%b')}",  # e.g. "Mon 14 Apr"
        "sleep": sleep,
        "workout": workout,
        "nutrition": nutrition,
        "mood": mood,
    }
