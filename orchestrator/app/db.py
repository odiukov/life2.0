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
        "nutrition": ["nutrition_log"],
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
        "SELECT agent, task_type AS type, input, created_at AS ts FROM tasks ORDER BY created_at DESC LIMIT 20"
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
