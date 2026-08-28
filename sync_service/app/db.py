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
            os.environ["POSTGRES_DSN"],
            init=_set_json_codec,
            min_size=1,
            max_size=int(os.environ.get("PG_POOL_MAX", "3")),
        )
    return _pool


async def list_user_credentials(service: str) -> list[tuple[str, dict]]:
    """Return [(user_id, payload)] for all users with credentials for the given service."""
    pool = await get_pool()
    async with pool.acquire() as conn:
        rows = await conn.fetch(
            "SELECT user_id::text, payload_dev FROM integrations_credentials "
            "WHERE service = $1 AND payload_dev IS NOT NULL",
            service,
        )
        return [(r["user_id"], r["payload_dev"]) for r in rows]


async def insert_rows(rows: list[dict], user_id: str | None = None) -> tuple[int, int]:
    """Upsert health_logs rows. Re-sync of an existing (user_id,source,type,recorded_at)
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
            # "INSERT 0 1" → row inserted or updated; "INSERT 0 0" → no-op (data identical)
            if result.endswith("1"):
                written += 1
            else:
                unchanged += 1
    return written, unchanged


async def update_token(user_id: str, service: str, field: str, value: str | dict) -> None:
    """Merge a single field into integrations_credentials.payload_dev (jsonb).

    Performs a jsonb merge operation: payload_dev || {field: value}
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        await conn.execute(
            "UPDATE integrations_credentials "
            "SET payload_dev = payload_dev || $1::jsonb "
            "WHERE user_id = $2::uuid AND service = $3",
            {field: value},
            user_id,
            service,
        )
