import asyncpg
import json
import os
from datetime import datetime, timezone, timedelta
from uuid import UUID
from zoneinfo import ZoneInfo

from shared.db import fetch_active_habits, fetch_habit_logs, fetch_active_medications, fetch_medication_logs, fetch_body_logs
from .recovery_context import fetch_recovery_shape

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
            user_id, agent, types, week_ago, two_weeks_ago
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
            user_id, agent, types, day_starts[0]
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
            int(hrv_row["hrv_rmssd"]) if hrv_row and hrv_row["hrv_rmssd"]
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
        user_id, day_starts[0]
    )
    sleep_map = {r["day"]: round(float(r["hours"]), 1) for r in sleep_daily}
    sleep_hours = [sleep_map.get(d.date(), 0) for d in day_starts]

    # Last 7 days workout minutes/day
    workout_daily = await pool.fetch(
        """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           SUM((data->>'duration_seconds')::float / 60) AS minutes
           FROM health_logs WHERE user_id = $1 AND agent='workout' AND type='activity' AND recorded_at >= $2
           GROUP BY day""",
        user_id, day_starts[0]
    )
    workout_map = {r["day"]: round(float(r["minutes"])) for r in workout_daily}
    workout_minutes = [workout_map.get(d.date(), 0) for d in day_starts]

    # Last 7 days nutrition calories/day (meal rows inserted by Yazio sync)
    nutrition_daily = await pool.fetch(
        """SELECT date_trunc('day', recorded_at AT TIME ZONE 'UTC')::date AS day,
           SUM((data->'totals'->>'kcal')::float) AS calories
           FROM health_logs WHERE user_id = $1 AND agent='nutrition' AND type='meal' AND recorded_at >= $2
           GROUP BY day""",
        user_id, day_starts[0]
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


async def get_tasks_today(agent: str) -> int:
    """Count tasks for an agent since midnight UTC today."""
    pool = await get_pool()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2",
        agent, today_start
    )
    return int(row["cnt"]) if row else 0


async def get_yesterday_metrics(user_id: UUID, use_today: bool = False) -> dict:
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
    _sleep_sql = """
        SELECT
            (data->>'duration_seconds')::float::int AS duration_seconds,
            (data->>'deep_sleep_seconds')::float::int AS deep_sleep_seconds,
            (data->>'hrv_weekly_avg')::float AS hrv_weekly_avg,
            (data->>'avg_hr')::float::int AS avg_hr,
            (data->>'score')::float::int AS score
        FROM health_logs
        WHERE user_id = $1 AND agent = 'sleep' AND type = 'sleep_session'
          AND source = $2
          AND recorded_at >= $3
        ORDER BY recorded_at DESC
        LIMIT 1
    """
    sleep_row = await pool.fetchrow(_sleep_sql, user_id, "garmin", day_start - timedelta(hours=36))
    _sleep_source = "Garmin"
    if not sleep_row:
        sleep_row = await pool.fetchrow(_sleep_sql, user_id, "SourceProxy", day_start - timedelta(hours=36))
        _sleep_source = "Apple Health"
    sleep = None
    if sleep_row:
        # Prefer hrv_status.hrv_rmssd (Garmin watch value) over hrv_weekly_avg
        # (sleep-DTO average — different Garmin metric, systematically diverges).
        hrv_row = await pool.fetchrow(
            "SELECT (data->>'hrv_rmssd')::float AS hrv_rmssd FROM health_logs "
            "WHERE user_id = $1 AND agent = 'sleep' AND type = 'hrv_status' "
            "  AND recorded_at >= $2 AND recorded_at < $3 "
            "ORDER BY recorded_at DESC LIMIT 1",
            user_id, day_start - timedelta(hours=36), day_end,
        )
        hrv = (
            int(hrv_row["hrv_rmssd"]) if hrv_row and hrv_row["hrv_rmssd"]
            else (int(sleep_row["hrv_weekly_avg"]) if sleep_row["hrv_weekly_avg"] else None)
        )
        sleep = {
            "duration_seconds": sleep_row["duration_seconds"] or 0,
            "deep_sleep_seconds": sleep_row["deep_sleep_seconds"] or 0,
            "hrv": hrv,
            "avg_hr": sleep_row["avg_hr"],
            "score": sleep_row["score"],
            "source": _sleep_source,
        }

    # Workout: prefer Garmin activity rows to avoid double-counting when both
    # Garmin and HealthKit report the same session. Fall back to any source if
    # Garmin has no data, then to HealthKit daily_stats as last resort.
    _workout_sql = """
        SELECT
            SUM((data->>'calories')::float)::int AS total_calories,
            SUM((data->>'distance_meters')::float)::int AS total_distance_meters,
            COUNT(*) AS activity_count,
            (array_agg(data->>'name' ORDER BY recorded_at DESC))[1] AS first_name,
            (array_agg(data->>'activity_type' ORDER BY recorded_at DESC))[1] AS first_type,
            AVG((data->>'avg_hr')::float)::int AS avg_hr,
            MAX(recorded_at) AS last_at
        FROM health_logs
        WHERE user_id = $1 AND agent = 'workout' AND type = 'activity'
          AND recorded_at >= $2 AND recorded_at < $3
          AND source = $4
    """
    workout_row = await pool.fetchrow(_workout_sql, user_id, day_start, day_end, "garmin")
    _workout_source = "Garmin"
    if not (workout_row and workout_row["activity_count"]):
        workout_row = await pool.fetchrow(_workout_sql, user_id, day_start, day_end, "apple_health")
        _workout_source = "Apple Health"
    workout = None
    if workout_row and workout_row["activity_count"]:
        workout = {
            "total_calories": workout_row["total_calories"] or 0,
            "total_distance_meters": workout_row["total_distance_meters"] or 0,
            "activity_count": int(workout_row["activity_count"]),
            "first_name": workout_row["first_name"] or "",
            "first_type": workout_row["first_type"] or "",
            "avg_hr": workout_row["avg_hr"] or 0,
            "source": _workout_source,
            "last_at": workout_row["last_at"],
        }
    else:
        # Fallback: HealthKit daily_stats accumulated by the aggregator.
        hk_workout_row = await pool.fetchrow(
            """
            SELECT
                (data->>'activeEnergyBurned')::float AS active_kcal,
                (data->>'exerciseTime')::float AS exercise_minutes,
                (data->>'distanceWalkingRunning')::float AS distance_m,
                (data->>'distanceCycling')::float AS distance_cycling_m
            FROM health_logs
            WHERE user_id = $1 AND type = 'daily_stats'
              AND recorded_at >= $2 AND recorded_at < $3
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            user_id, day_start, day_end,
        )
        if hk_workout_row and hk_workout_row["exercise_minutes"]:
            mins = int(hk_workout_row["exercise_minutes"] or 0)
            dist = int((hk_workout_row["distance_m"] or 0) + (hk_workout_row["distance_cycling_m"] or 0))
            workout = {
                "total_calories": int(hk_workout_row["active_kcal"] or 0),
                "total_distance_meters": dist,
                "activity_count": 1,
                "first_name": f"{mins} min active",
                "first_type": "activity",
                "source": "Apple Health",
            }

    # Nutrition: prefer Yazio meal rows (source='yazio') to avoid double-counting
    # when Apple Health also writes a daily_total meal row for the same day.
    nutrition_row = await pool.fetchrow(
        """
        SELECT
            SUM((data->'totals'->>'kcal')::float) AS kcal,
            SUM((data->'totals'->>'protein_g')::float) AS protein_g,
            SUM((data->'totals'->>'carbs_g')::float) AS carbs_g,
            SUM((data->'totals'->>'fat_g')::float) AS fat_g
        FROM health_logs
        WHERE user_id = $1 AND agent = 'nutrition' AND type = 'meal'
          AND source = 'yazio'
          AND recorded_at >= $2 AND recorded_at < $3
        """,
        user_id, day_start, day_end,
    )
    nutrition = None
    if nutrition_row and nutrition_row["kcal"] is not None:
        nutrition = {
            "kcal": round(nutrition_row["kcal"] or 0),
            "protein_g": round(nutrition_row["protein_g"] or 0),
            "carbs_g": round(nutrition_row["carbs_g"] or 0),
            "fat_g": round(nutrition_row["fat_g"] or 0),
            "source": "Yazio",
        }
    else:
        hk_nutrition_row = await pool.fetchrow(
            """
            SELECT
                (data->>'dietaryEnergyConsumed')::float AS kcal,
                (data->>'dietaryProtein')::float AS protein_g,
                (data->>'dietaryCarbohydrates')::float AS carbs_g,
                (data->>'dietaryFatTotal')::float AS fat_g
            FROM health_logs
            WHERE user_id = $1 AND type = 'daily_stats'
              AND recorded_at >= $2 AND recorded_at < $3
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            user_id, day_start, day_end,
        )
        if hk_nutrition_row and hk_nutrition_row["kcal"]:
            nutrition = {
                "kcal": round(hk_nutrition_row["kcal"] or 0),
                "protein_g": round(hk_nutrition_row["protein_g"] or 0),
                "carbs_g": round(hk_nutrition_row["carbs_g"] or 0),
                "fat_g": round(hk_nutrition_row["fat_g"] or 0),
                "source": "Apple Health",
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
        WHERE user_id = $1 AND type = 'mood'
          AND recorded_at >= $2 AND recorded_at < $3
        """,
        user_id, day_start, day_end,
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

    # Habits: two-piece roll-up (yesterday backward + today todo).
    habit_defs = await fetch_active_habits(user_id)
    habits = None
    if habit_defs:
        yesterday_key = yesterday.isoformat()
        today_local = now_kyiv.date()
        today_key = today_local.isoformat()
        logs = await fetch_habit_logs(user_id, days=180)
        by_habit_day: dict[tuple[str, str], list[dict]] = {}
        for r in logs:
            hid = (r.get("data") or {}).get("habit_id")
            if not hid:
                continue
            d_key = r["recorded_at"].astimezone(kyiv).date().isoformat()
            by_habit_day.setdefault((hid, d_key), []).append(r.get("data") or {})

        _WEEKDAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]

        def _expected_on(h: dict, weekday_idx: int) -> bool:
            if h["cadence_type"] == "daily":
                return True
            return _WEEKDAYS[weekday_idx] in (h.get("cadence_days") or [])

        def _complete(h: dict, rows: list[dict]) -> bool:
            if not rows:
                return False
            if h["kind"] == "boolean":
                return any(r.get("completed") for r in rows)
            total = 0.0
            for r in rows:
                try:
                    total += float(r.get("value") or 0)
                except (TypeError, ValueError):
                    continue
            tgt = h.get("target_value") or 0
            return total >= float(tgt) if tgt > 0 else total > 0

        def _streak(h: dict) -> int:
            cursor = today_local
            count = 0
            for _ in range(400):
                weekday_idx = (cursor.toordinal() - 1) % 7  # mon=0
                key = cursor.isoformat()
                if h["cadence_type"] == "weekly" and not _expected_on(h, weekday_idx):
                    cursor = cursor - timedelta(days=1)
                    continue
                if _complete(h, by_habit_day.get((h["id"], key), [])):
                    count += 1
                    cursor = cursor - timedelta(days=1)
                else:
                    break
            return count

        yesterday_weekday = (yesterday.toordinal() - 1) % 7
        expected_y, completed_y, missed = 0, 0, []
        for h in habit_defs:
            if not _expected_on(h, yesterday_weekday):
                continue
            expected_y += 1
            if _complete(h, by_habit_day.get((h["id"], yesterday_key), [])):
                completed_y += 1
            else:
                missed.append(h["name"])

        streaks = sorted(
            ({"name": h["name"], "streak": _streak(h)} for h in habit_defs),
            key=lambda x: -x["streak"],
        )
        top_streaks = [s for s in streaks if s["streak"] >= 2][:3]

        today_weekday = (today_local.toordinal() - 1) % 7
        today_items = []
        for h in habit_defs:
            if not _expected_on(h, today_weekday):
                continue
            today_items.append({
                "name": h["name"],
                "done": _complete(h, by_habit_day.get((h["id"], today_key), [])),
            })

        habits = {
            "expected_yesterday": expected_y,
            "completed_yesterday": completed_y,
            "missed_names": missed,
            "top_streaks": top_streaks,
            "today_items": today_items,
            "today_names": [it["name"] for it in today_items],
        }

    # Recovery — target = yesterday in Kyiv TZ.
    recovery = await fetch_recovery_shape(user_id, yesterday)

    # Calendar — forward-looking (today, not yesterday).
    from .calendar_context import fetch_calendar_shape
    calendar = await fetch_calendar_shape(now_kyiv.date(), user_id)

    # Medication: current active list + last 7d of taken events
    med_active = []
    med_logs = []
    try:
        med_rows = await fetch_active_medications(user_id)
        med_active = [{"name": m["name"], "schedule": m["schedule"]} for m in med_rows]
        log_rows = await fetch_medication_logs(user_id, days=7)
        med_logs = [
            {"name": (r.get("data") or {}).get("name"),
             "recorded_at": r.get("recorded_at")}
            for r in log_rows
        ]
    except Exception as e:
        # don't fail the whole summary if medication query breaks
        import logging
        logging.getLogger(__name__).warning("medication metrics failed: %s", e)

    medication = (
        {"active": med_active, "logs": med_logs}
        if med_active else None
    )

    try:
        body_rows_raw = await fetch_body_logs(user_id, limit=60)
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("body metrics fetch failed: %s", e)
        body_rows_raw = []

    body = None
    if body_rows_raw:
        recent = []
        for r in body_rows_raw:
            d = r.get("data") or {}
            recent.append({
                "weight_kg": d.get("weight_kg"),
                "body_fat_pct": d.get("body_fat_pct"),
                "lean_mass_kg": d.get("lean_mass_kg"),
                "bmi": d.get("bmi"),
                "recorded_at": r["recorded_at"],
            })
        # "recent_90d" is aspirational — shape is up-to-60 most-recent rows, no
        # time filter (see fetch_body_logs). Real window is cadence-dependent.
        body = {"latest": recent[0], "recent_90d": recent}

    # Apple Health last sync timestamp
    hk_sync_row = await pool.fetchrow(
        """
        SELECT MAX(recorded_at) AS last_sync
        FROM health_logs
        WHERE user_id = $1
          AND source IN ('SourceProxy', 'apple_health', 'HealthKit')
        """,
        user_id,
    )
    healthkit_last_sync = hk_sync_row["last_sync"] if hk_sync_row else None

    # HRV 30-day baseline (requires ≥10 readings to be meaningful)
    if sleep:
        hrv_hist_row = await pool.fetchrow(
            """
            SELECT
                AVG((data->>'hrv_weekly_avg')::float) AS hrv_30d_avg,
                COUNT(*) AS hrv_count
            FROM health_logs
            WHERE user_id = $1
              AND agent = 'sleep'
              AND type = 'sleep_session'
              AND recorded_at >= NOW() - INTERVAL '30 days'
              AND data->>'hrv_weekly_avg' IS NOT NULL
            """,
            user_id,
        )
        if hrv_hist_row and int(hrv_hist_row["hrv_count"] or 0) >= 10:
            sleep["hrv_30d_avg"] = float(hrv_hist_row["hrv_30d_avg"])

    return {
        "date": f"{yesterday.strftime('%a')} {yesterday.day} {yesterday.strftime('%b')}",  # e.g. "Mon 14 Apr"
        "sleep": sleep,
        "workout": workout,
        "nutrition": nutrition,
        "mood": mood,
        "habits": habits,
        "recovery": recovery,
        "calendar": calendar,
        "medication": medication,
        "body": body,
        "healthkit_last_sync": healthkit_last_sync,
    }


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
        user_id, days,
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
        user_id, days,
    )
    return [
        {"date": r["date"], "value": float(r["value"]),
         "label": f"{int(r['value'])} min" if r["value"] > 0 else "—"}
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
        user_id, days,
    )
    return [
        {"date": r["date"], "value": float(r["value"]),
         "label": f"{int(r['value'])} kcal" if r["value"] > 0 else "—"}
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
        user_id, days,
    )
    return [
        {"date": r["date"], "value": float(r["value"]),
         "label": f"{r['value']:.1f}" if r["value"] > 0 else "—"}
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
        result.append({
            "date": key,
            "value": float(hrv),
            "label": f"{int(hrv)} ms" if hrv else "—",
        })
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
        user_id, days,
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
        user_id, days,
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
        user_id, days,
    )
    return [
        {"date": r["date"], "value": float(r["value"]),
         "label": f"${r['value']:.0f}" if r["value"] > 0 else "—"}
        for r in rows
    ]
