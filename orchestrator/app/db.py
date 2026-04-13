import asyncpg
import json
import os
from datetime import datetime, timezone, timedelta

_pool: asyncpg.Pool | None = None


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        _pool = await asyncpg.create_pool(os.environ["POSTGRES_DSN"], init=_set_json_codec)
    return _pool


async def get_stats() -> dict:
    """Return per-agent task counts (this week vs prev week) and last 10 tasks as activity feed."""
    pool = await get_pool()
    now = datetime.now(timezone.utc)
    week_ago = now - timedelta(days=7)
    two_weeks_ago = now - timedelta(days=14)

    agents = ["sleep", "workout", "nutrition"]
    agent_stats = {}
    for agent in agents:
        this_week = await pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2",
            agent, week_ago
        )
        prev_week = await pool.fetchrow(
            "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2 AND created_at < $3",
            agent, two_weeks_ago, week_ago
        )
        tw = int(this_week["cnt"]) if this_week else 0
        pw = int(prev_week["cnt"]) if prev_week else 0
        agent_stats[agent] = {"tasks_week": tw, "tasks_prev_week": pw, "delta": tw - pw}

    activity_rows = await pool.fetch(
        "SELECT agent, task_type, input, created_at FROM tasks "
        "ORDER BY created_at DESC LIMIT 10"
    )
    activity = [
        {
            "agent": r["agent"],
            "task_type": r["task_type"],
            "message": (r["input"] or {}).get("message", "")[:80],
            "created_at": r["created_at"].isoformat(),
        }
        for r in activity_rows
    ]

    return {"agents": agent_stats, "activity": activity}


async def get_tasks_today(agent: str) -> int:
    """Count tasks for an agent since midnight UTC today."""
    pool = await get_pool()
    today_start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    row = await pool.fetchrow(
        "SELECT COUNT(*) as cnt FROM tasks WHERE agent=$1 AND created_at >= $2",
        agent, today_start
    )
    return int(row["cnt"]) if row else 0
