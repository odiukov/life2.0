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
    """Insert health_logs rows. Skips duplicates via unique index.
    Returns (inserted, skipped).
    """
    if not rows:
        return 0, 0
    pool = await get_pool()
    inserted = 0
    skipped = 0
    async with pool.acquire() as conn:
        for row in rows:
            result = await conn.execute(
                """
                INSERT INTO health_logs (agent, type, data, recorded_at, source)
                VALUES ($1, $2, $3, $4, $5)
                ON CONFLICT (source, type, recorded_at) DO NOTHING
                """,
                row["agent"],
                row["type"],
                row["data"],
                row["recorded_at"],
                row["source"],
            )
            # result string is "INSERT 0 1" (inserted) or "INSERT 0 0" (skipped)
            if result.endswith("1"):
                inserted += 1
            else:
                skipped += 1
    return inserted, skipped
