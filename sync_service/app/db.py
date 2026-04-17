import asyncpg
import json
import os

_pool: asyncpg.Pool | None = None


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec(
        "jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )
    await conn.set_type_codec(
        "json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog"
    )


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(
            os.environ["POSTGRES_DSN"], init=_set_json_codec
        )
    return _pool


async def insert_rows(rows: list[dict]) -> tuple[int, int]:
    """Upsert health_logs rows. Re-sync of an existing (source,type,recorded_at)
    row replaces its `data` so partial syncs (e.g. missing recipes/AI meals) heal
    on the next run. Rows whose `data` is identical are left untouched.

    Returns (written, unchanged) — written counts inserts + actual updates.
    """
    if not rows:
        return 0, 0
    pool = await get_pool()
    written = 0
    unchanged = 0
    async with pool.acquire() as conn:
        for row in rows:
            result = await conn.execute(
                """
                INSERT INTO health_logs (agent, type, data, recorded_at, source)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (source, type, recorded_at) DO UPDATE
                  SET data = EXCLUDED.data
                  WHERE health_logs.data IS DISTINCT FROM EXCLUDED.data
                """,
                row["agent"],
                row["type"],
                row["data"],
                row["recorded_at"],
                row["source"],
            )
            # "INSERT 0 1" → row inserted or updated; "INSERT 0 0" → no-op (data identical)
            if result.endswith("1"):
                written += 1
            else:
                unchanged += 1
    return written, unchanged
