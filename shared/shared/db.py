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
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO tasks (agent, task_type, input, output) VALUES ($1, $2, $3, $4)",
        agent, task_type, input_, output
    )
