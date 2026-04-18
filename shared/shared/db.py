import asyncpg
import json
import os

_pool: asyncpg.Pool | None = None


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"], init=_set_json_codec)
    return _pool


async def fetch_recent_logs(agent: str, limit: int = 20) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE agent = $1 ORDER BY recorded_at DESC LIMIT $2",
        agent, limit
    )
    return [dict(r) for r in rows]


async def insert_log(agent: str, type_: str, data: dict, source: str = "manual") -> None:
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO health_logs (agent, type, data, source) VALUES ($1, $2, $3, $4)",
        agent, type_, data, source
    )


async def insert_task(agent: str, task_type: str, input_: dict, output: str) -> None:
    """Legacy single-row insert — kept for callers that don't have task_id yet."""
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO tasks (agent, task_type, input, output) VALUES ($1, $2, $3, $4)",
        agent, task_type, input_, output
    )


async def insert_task_record(
    *,
    agent: str,
    task_id: str,
    context_id: str | None,
    skill_id: str,
    input_: dict,
    output: str,
    state: str = "completed",
) -> None:
    """Persist a completed A2A task with its A2A identifiers."""
    pool = await get_pool()
    await pool.execute(
        """
        INSERT INTO tasks (task_id, context_id, agent, skill_id, input, output, state)
        VALUES ($1, $2, $3, $4, $5, $6, $7)
        ON CONFLICT (task_id) DO UPDATE SET
            output = EXCLUDED.output,
            state = EXCLUDED.state,
            updated_at = NOW()
        """,
        task_id, context_id, agent, skill_id, input_, output, state,
    )


async def fetch_body_logs(limit: int = 30) -> list[dict]:
    """Return latest body_composition rows regardless of the `agent` column.

    Historical rows were written with agent='workout' by map_body_composition;
    new rows may land under agent='body'. Filter purely by type to tolerate both.
    """
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE type = $1 ORDER BY recorded_at DESC LIMIT $2",
        "body_composition", limit,
    )
    return [dict(r) for r in rows]


async def fetch_mood_logs(limit: int = 30) -> list[dict]:
    """Return latest mood rows ordered by recorded_at DESC."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE type = 'mood' ORDER BY recorded_at DESC LIMIT $1",
        limit,
    )
    return [dict(r) for r in rows]


async def fetch_active_habits() -> list[dict]:
    """Return active habit definitions ordered by created_at ASC."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id::text AS id, name, kind, cadence_type, cadence_days, target_value, unit, "
        "created_at FROM habits WHERE archived_at IS NULL "
        "ORDER BY created_at ASC"
    )
    return [dict(r) for r in rows]


async def fetch_habit_logs(habit_id: str | None = None, days: int = 30) -> list[dict]:
    """Return habit check-in rows. If habit_id is given, filter to that habit only."""
    pool = await get_pool()
    if habit_id:
        rows = await pool.fetch(
            "SELECT type, data, recorded_at, source FROM health_logs "
            "WHERE type = 'habit' AND data->>'habit_id' = $1 "
            "  AND recorded_at >= now() - make_interval(days => $2) "
            "ORDER BY recorded_at DESC",
            habit_id, days,
        )
    else:
        rows = await pool.fetch(
            "SELECT type, data, recorded_at, source FROM health_logs "
            "WHERE type = 'habit' "
            "  AND recorded_at >= now() - make_interval(days => $1) "
            "ORDER BY recorded_at DESC",
            days,
        )
    return [dict(r) for r in rows]


async def insert_habit(
    name: str, kind: str, cadence_type: str,
    cadence_days: list[str] | None = None,
    target_value: float | None = None,
    unit: str | None = None,
) -> str:
    """Insert a new habit row. Returns the UUID as string. Raises on unique-name conflict."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO habits (name, kind, cadence_type, cadence_days, target_value, unit) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id::text",
        name, kind, cadence_type, cadence_days, target_value, unit,
    )
    return row["id"]


async def archive_habit(habit_id: str) -> bool:
    """Soft-delete a habit. Returns True if a row was updated."""
    pool = await get_pool()
    status = await pool.execute(
        "UPDATE habits SET archived_at = now() "
        "WHERE id = $1::uuid AND archived_at IS NULL",
        habit_id,
    )
    return status.endswith(" 1")


async def fetch_recovery_metrics(days: int = 7) -> dict[str, dict]:
    """Return per-day recovery metrics keyed by Kyiv-TZ date ISO string.

    Joins two health_logs types in memory:
      - 'sleep_session' → hrv_weekly_avg, score
      - 'daily_stats'   → resting_hr, stress_avg, body_battery_min/max

    Each day's dict has six fields, any of which may be None if that row is
    missing or the JSON field is absent.
    """
    from zoneinfo import ZoneInfo
    pool = await get_pool()
    _tz = ZoneInfo("Europe/Kyiv")

    sleep_rows = await pool.fetch(
        "SELECT recorded_at, "
        "       (data->>'hrv_weekly_avg')::float AS hrv, "
        "       (data->>'score')::int AS score "
        "FROM health_logs "
        "WHERE type = 'sleep_session' "
        "  AND recorded_at >= now() - make_interval(days => $1)",
        days,
    )
    stats_rows = await pool.fetch(
        "SELECT recorded_at, "
        "       (data->>'resting_hr')::int AS rhr, "
        "       (data->>'stress_avg')::int AS stress, "
        "       (data->>'body_battery_min')::int AS bb_min, "
        "       (data->>'body_battery_max')::int AS bb_max "
        "FROM health_logs "
        "WHERE type = 'daily_stats' "
        "  AND recorded_at >= now() - make_interval(days => $1)",
        days,
    )

    out: dict[str, dict] = {}
    for r in sleep_rows:
        key = r["recorded_at"].astimezone(_tz).date().isoformat()
        day = out.setdefault(key, {
            "hrv": None, "rhr": None, "stress": None,
            "bb_min": None, "bb_max": None, "sleep_score": None,
        })
        if r["hrv"] is not None:
            day["hrv"] = r["hrv"]
        if r["score"] is not None:
            day["sleep_score"] = r["score"]
    for r in stats_rows:
        key = r["recorded_at"].astimezone(_tz).date().isoformat()
        day = out.setdefault(key, {
            "hrv": None, "rhr": None, "stress": None,
            "bb_min": None, "bb_max": None, "sleep_score": None,
        })
        if r["rhr"] is not None:
            day["rhr"] = r["rhr"]
        if r["stress"] is not None:
            day["stress"] = r["stress"]
        if r["bb_min"] is not None:
            day["bb_min"] = r["bb_min"]
        if r["bb_max"] is not None:
            day["bb_max"] = r["bb_max"]
    return out
