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
        "SELECT id, name, kind, cadence_type, cadence_days, target_value, unit, "
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
