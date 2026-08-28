import asyncpg
import json
import os
import pathlib
from uuid import UUID

_pool: asyncpg.Pool | None = None

# ---------------------------------------------------------------------------
# Schema-migration bootstrap
# ---------------------------------------------------------------------------

# Locate supabase/migrations/ relative to this file:
#   shared/shared/db.py → shared/ → repo-root → supabase/migrations/
_REPO_ROOT = pathlib.Path(__file__).parent.parent.parent
_MIGRATIONS_DIR = _REPO_ROOT / "supabase" / "migrations"

_CREATE_SCHEMA_MIGRATIONS = """
CREATE TABLE IF NOT EXISTS public.schema_migrations (
    version     text PRIMARY KEY,
    applied_at  timestamptz NOT NULL DEFAULT now()
);
"""


async def init_db_pool() -> asyncpg.Pool:
    """Return (and create if needed) the connection pool, then apply any
    pending migrations from supabase/migrations/*.sql in lexicographic order.

    This makes local docker-postgres startup idempotent: already-applied
    migrations are skipped via the schema_migrations tracking table.
    """
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Ensure the migrations tracking table exists
            await conn.execute(_CREATE_SCHEMA_MIGRATIONS)

        if not _MIGRATIONS_DIR.exists():
            return pool

        # Collect applied versions
        applied = {
            row["version"]
            for row in await conn.fetch(
                "SELECT version FROM public.schema_migrations ORDER BY version"
            )
        }

        # Apply each migration file in lexicographic order
        for migration_file in sorted(_MIGRATIONS_DIR.glob("*.sql")):
            version = migration_file.stem  # filename without .sql extension
            if version in applied:
                continue
            sql = migration_file.read_text(encoding="utf-8")
            async with conn.transaction():
                await conn.execute(sql)
                await conn.execute(
                    "INSERT INTO public.schema_migrations (version) VALUES ($1)",
                    version,
                )

    return pool


async def close_db_pool() -> None:
    """Close the connection pool if open."""
    global _pool
    if _pool is not None:
        await _pool.close()
        _pool = None


async def _set_json_codec(conn: asyncpg.Connection) -> None:
    await conn.set_type_codec("jsonb", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")
    await conn.set_type_codec("json", encoder=json.dumps, decoder=json.loads, schema="pg_catalog")


async def get_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        # Default asyncpg pool is min=10/max=10 per process. With 8 agents + orchestrator
        # + sync_service + psycopg3 checkpointer, that easily exceeds Postgres default
        # max_connections=100. Keep per-service budgets tight for this single-user stack.
        _pool = await asyncpg.create_pool(
            os.environ["POSTGRES_DSN"],
            init=_set_json_codec,
            min_size=1,
            max_size=int(os.environ.get("PG_POOL_MAX", "3")),
        )
    return _pool


# ---------------------------------------------------------------------------
# Generic health_logs helpers (user-scoped)
# ---------------------------------------------------------------------------

async def insert_health_log(
    user_id: UUID,
    type_: str,
    recorded_at,
    data: dict,
    agent: str = "system",
    source: str = "manual",
) -> UUID:
    """Insert a health_log row scoped to user_id. Returns the new row's UUID."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO health_logs (user_id, agent, type, recorded_at, data, source) "
        "VALUES ($1, $2, $3, $4, $5, $6) RETURNING id",
        user_id, agent, type_, recorded_at, data, source,
    )
    return row["id"]


async def fetch_health_logs(
    user_id: UUID,
    type_: str,
    limit: int = 20,
) -> list[dict]:
    """Fetch health_log rows for user_id filtered by type, ordered DESC."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id, agent, type, data, recorded_at, source FROM health_logs "
        "WHERE user_id = $1 AND type = $2 ORDER BY recorded_at DESC LIMIT $3",
        user_id, type_, limit,
    )
    return [dict(r) for r in rows]


async def fetch_recent_logs(
    user_id: UUID,
    agent: str,
    limit: int = 20,
) -> list[dict]:
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE user_id = $1 AND agent = $2 ORDER BY recorded_at DESC LIMIT $3",
        user_id, agent, limit,
    )
    return [dict(r) for r in rows]


async def insert_log(
    user_id: UUID,
    agent: str,
    type_: str,
    data: dict,
    source: str = "manual",
) -> None:
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO health_logs (user_id, agent, type, data, source) VALUES ($1, $2, $3, $4, $5)",
        user_id, agent, type_, data, source,
    )


# ---------------------------------------------------------------------------
# Tasks (NOT user-scoped — tasks table has no user_id column yet)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Body composition
# ---------------------------------------------------------------------------

async def fetch_body_logs(user_id: UUID, limit: int = 30) -> list[dict]:
    """Return latest body_composition rows for user_id.

    Historical rows were written with agent='workout' by map_body_composition;
    new rows may land under agent='body'. Filter purely by type to tolerate both.
    """
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE user_id = $1 AND type = $2 ORDER BY recorded_at DESC LIMIT $3",
        user_id, "body_composition", limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Mood
# ---------------------------------------------------------------------------

async def fetch_mood_logs(user_id: UUID, limit: int = 30) -> list[dict]:
    """Return latest mood rows ordered by recorded_at DESC."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT type, data, recorded_at, source FROM health_logs "
        "WHERE user_id = $1 AND type = 'mood' ORDER BY recorded_at DESC LIMIT $2",
        user_id, limit,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Habits
# ---------------------------------------------------------------------------

async def fetch_active_habits(user_id: UUID) -> list[dict]:
    """Return active habit definitions for user_id ordered by created_at ASC."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id::text AS id, name, kind, cadence_type, cadence_days, target_value, unit, "
        "created_at FROM habits WHERE user_id = $1 AND archived_at IS NULL "
        "ORDER BY created_at ASC",
        user_id,
    )
    return [dict(r) for r in rows]


async def fetch_habit_logs(
    user_id: UUID,
    habit_id: str | None = None,
    days: int = 30,
) -> list[dict]:
    """Return habit check-in rows for user_id. If habit_id is given, filter to that habit only."""
    pool = await get_pool()
    if habit_id:
        rows = await pool.fetch(
            "SELECT type, data, recorded_at, source FROM health_logs "
            "WHERE user_id = $1 AND type = 'habit' AND data->>'habit_id' = $2 "
            "  AND recorded_at >= now() - make_interval(days => $3) "
            "ORDER BY recorded_at DESC",
            user_id, habit_id, days,
        )
    else:
        rows = await pool.fetch(
            "SELECT type, data, recorded_at, source FROM health_logs "
            "WHERE user_id = $1 AND type = 'habit' "
            "  AND recorded_at >= now() - make_interval(days => $2) "
            "ORDER BY recorded_at DESC",
            user_id, days,
        )
    return [dict(r) for r in rows]


async def insert_habit(
    user_id: UUID,
    name: str,
    kind: str,
    cadence_type: str,
    cadence_days: list[str] | None = None,
    target_value: float | None = None,
    unit: str | None = None,
) -> str:
    """Insert a new habit row for user_id. Returns the UUID as string. Raises on unique-name conflict."""
    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO habits (user_id, name, kind, cadence_type, cadence_days, target_value, unit) "
        "VALUES ($1, $2, $3, $4, $5, $6, $7) RETURNING id::text",
        user_id, name, kind, cadence_type, cadence_days, target_value, unit,
    )
    return row["id"]


async def archive_habit(user_id: UUID, habit_id: str) -> bool:
    """Soft-delete a habit for user_id. Returns True if a row was updated."""
    pool = await get_pool()
    status = await pool.execute(
        "UPDATE habits SET archived_at = now() "
        "WHERE user_id = $1 AND id = $2::uuid AND archived_at IS NULL",
        user_id, habit_id,
    )
    return status.endswith(" 1")


# ---------------------------------------------------------------------------
# Recovery metrics
# ---------------------------------------------------------------------------

async def fetch_recovery_metrics(user_id: UUID, days: int = 7) -> dict[str, dict]:
    """Return per-day recovery metrics keyed by Kyiv-TZ date ISO string.

    Joins three health_logs types in memory:
      - 'hrv_status'    → hrv_rmssd (Garmin HRV Status API; matches the watch widget)
      - 'sleep_session' → hrv_weekly_avg (fallback HRV), score, duration_seconds, awake_seconds
      - 'daily_stats'   → resting_hr, stress_avg, body_battery_min/max

    HRV resolution: prefer hrv_status.hrv_rmssd (the value the watch shows) and
    fall back to sleep_session.hrv_weekly_avg only when the HRV Status row is
    missing for that day. The two metrics are computed differently by Garmin
    (RMSSD on 5-min deep-sleep windows vs. average HRV across the whole night),
    so they do not match — use the watch-equivalent one.

    Each day's dict has keys for both the legacy Garmin names (hrv, rhr, stress,
    bb_min, bb_max, sleep_score) and the compute_bucket contract names
    (hrv_sdnn, sleep_duration_h, sleep_efficiency_pct) so that both the recovery
    agent prompt and shared.recovery.compute_bucket work with the same data.
    """
    from zoneinfo import ZoneInfo
    pool = await get_pool()
    _tz = ZoneInfo("Europe/Kyiv")

    sleep_rows = await pool.fetch(
        "SELECT recorded_at, "
        "       (data->>'hrv_weekly_avg')::float AS hrv, "
        "       (data->>'score')::int AS score, "
        "       (data->>'duration_seconds')::float AS duration_seconds, "
        "       (data->>'awake_seconds')::float AS awake_seconds "
        "FROM health_logs "
        "WHERE user_id = $1 AND type = 'sleep_session' "
        "  AND recorded_at >= now() - make_interval(days => $2)",
        user_id, days,
    )
    stats_rows = await pool.fetch(
        "SELECT recorded_at, "
        "       (data->>'resting_hr')::int AS rhr, "
        "       (data->>'stress_avg')::int AS stress, "
        "       (data->>'body_battery_min')::int AS bb_min, "
        "       (data->>'body_battery_max')::int AS bb_max "
        "FROM health_logs "
        "WHERE user_id = $1 AND type = 'daily_stats' "
        "  AND recorded_at >= now() - make_interval(days => $2)",
        user_id, days,
    )
    hrv_rows = await pool.fetch(
        "SELECT recorded_at, "
        "       (data->>'hrv_rmssd')::float AS hrv_rmssd "
        "FROM health_logs "
        "WHERE user_id = $1 AND type = 'hrv_status' "
        "  AND recorded_at >= now() - make_interval(days => $2)",
        user_id, days,
    )

    def _empty_day() -> dict:
        return {
            "hrv": None, "rhr": None, "stress": None,
            "bb_min": None, "bb_max": None, "sleep_score": None,
            "hrv_sdnn": None, "sleep_duration_h": None, "sleep_efficiency_pct": None,
        }

    out: dict[str, dict] = {}
    for r in sleep_rows:
        key = r["recorded_at"].astimezone(_tz).date().isoformat()
        day = out.setdefault(key, _empty_day())
        if r["hrv"] is not None:
            day["hrv"] = r["hrv"]
            day["hrv_sdnn"] = r["hrv"]  # alias for compute_bucket
        if r["score"] is not None:
            day["sleep_score"] = r["score"]
        dur = r["duration_seconds"]
        awake = r["awake_seconds"]
        if dur:
            day["sleep_duration_h"] = round(dur / 3600, 2)
            if awake is not None:
                day["sleep_efficiency_pct"] = round(
                    max(0.0, (dur - awake) / dur * 100), 1
                )
    for r in stats_rows:
        key = r["recorded_at"].astimezone(_tz).date().isoformat()
        day = out.setdefault(key, _empty_day())
        if r["rhr"] is not None:
            day["rhr"] = r["rhr"]
        if r["stress"] is not None:
            day["stress"] = r["stress"]
        if r["bb_min"] is not None:
            day["bb_min"] = r["bb_min"]
        if r["bb_max"] is not None:
            day["bb_max"] = r["bb_max"]
    # Apply HRV Status override last so it wins over the sleep-DTO fallback.
    for r in hrv_rows:
        if r["hrv_rmssd"] is None:
            continue
        key = r["recorded_at"].astimezone(_tz).date().isoformat()
        day = out.setdefault(key, _empty_day())
        day["hrv"] = r["hrv_rmssd"]
        day["hrv_sdnn"] = r["hrv_rmssd"]
    return out


# ---------------------------------------------------------------------------
# Medications (0005)
# ---------------------------------------------------------------------------
import re as _re_meds

_MED_NAME_NON_ALNUM = _re_meds.compile(r"[^a-z0-9]+")


def _normalize_med_name(raw: str) -> str:
    if not raw:
        return ""
    return _MED_NAME_NON_ALNUM.sub("-", raw.strip().lower()).strip("-")


async def insert_medication(
    user_id: UUID,
    name: str,
    dose: str | None,
    schedule: str,
    notes: str | None = None,
) -> str:
    """Insert a new medication row for user_id. Returns the UUID as string. Raises on unique-name conflict."""
    canonical = _normalize_med_name(name)
    if not canonical:
        raise ValueError("medication name cannot be empty")
    pool = await get_pool()
    row = await pool.fetchrow(
        "INSERT INTO medications (user_id, name, dose, schedule, notes) "
        "VALUES ($1, $2, $3, $4, $5) RETURNING id::text",
        user_id, canonical, dose, schedule, notes,
    )
    return row["id"]


async def fetch_active_medications(user_id: UUID) -> list[dict]:
    """Return active medication definitions for user_id ordered by created_at ASC."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT id::text AS id, name, dose, schedule, notes, created_at "
        "FROM medications WHERE user_id = $1 AND archived_at IS NULL ORDER BY created_at ASC",
        user_id,
    )
    return [dict(r) for r in rows]


async def find_medication_by_name(user_id: UUID, raw: str) -> dict | None:
    """Find an active medication by name for user_id (canonicalizes input). Returns None if not found."""
    canonical = _normalize_med_name(raw)
    if not canonical:
        return None
    pool = await get_pool()
    row = await pool.fetchrow(
        "SELECT id::text AS id, name, dose, schedule, notes, created_at "
        "FROM medications WHERE user_id = $1 AND name = $2 AND archived_at IS NULL",
        user_id, canonical,
    )
    return dict(row) if row else None


async def archive_medication(user_id: UUID, med_id: str) -> bool:
    """Soft-delete a medication for user_id. Returns True if a row was updated."""
    pool = await get_pool()
    status = await pool.execute(
        "UPDATE medications SET archived_at = now() "
        "WHERE user_id = $1 AND id = $2::uuid AND archived_at IS NULL",
        user_id, med_id,
    )
    return status.endswith(" 1")


async def fetch_medication_logs(
    user_id: UUID,
    med_name: str | None = None,
    days: int = 30,
) -> list[dict]:
    """health_logs rows where type='medication_taken' for user_id. Optional filter by name."""
    pool = await get_pool()
    if med_name:
        canonical = _normalize_med_name(med_name)
        rows = await pool.fetch(
            "SELECT id, recorded_at, data, source FROM health_logs "
            "WHERE user_id = $1 AND type = 'medication_taken' AND data->>'name' = $2 "
            "  AND recorded_at > now() - ($3::text || ' days')::interval "
            "ORDER BY recorded_at DESC",
            user_id, canonical, str(days),
        )
    else:
        rows = await pool.fetch(
            "SELECT id, recorded_at, data, source FROM health_logs "
            "WHERE user_id = $1 AND type = 'medication_taken' "
            "  AND recorded_at > now() - ($2::text || ' days')::interval "
            "ORDER BY recorded_at DESC",
            user_id, str(days),
        )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Finance helpers (Payoneer CSV ingest + category cache + queries)
# ---------------------------------------------------------------------------

async def upsert_finance_rows(user_id: UUID, rows: list[dict]) -> tuple[int, int]:
    """Insert rows into finance_transactions for user_id keyed on (user_id, txn_id).
    Returns (inserted, skipped). Skipped = rows that conflicted and were ignored."""
    if not rows:
        return 0, 0
    pool = await get_pool()
    inserted = 0
    async with pool.acquire() as conn:
        async with conn.transaction():
            for r in rows:
                res = await conn.execute(
                    """
                    INSERT INTO finance_transactions
                      (user_id, txn_id, ts, direction, amount, currency, description, raw)
                    VALUES ($1, $2, $3, $4, $5, $6, $7, $8)
                    ON CONFLICT (user_id, txn_id) DO NOTHING
                    """,
                    user_id, r["txn_id"], r["ts"], r["direction"],
                    r["amount"], r["currency"], r.get("description"),
                    r.get("raw") or {},
                )
                # asyncpg execute returns "INSERT 0 1" on success, "INSERT 0 0" on
                # ON CONFLICT DO NOTHING. Parse the trailing count.
                if res.split()[-1] == "1":
                    inserted += 1
    return inserted, len(rows) - inserted


async def fetch_uncategorized_ids(user_id: UUID) -> list[str]:
    """Return txn_ids of rows for user_id that still have category IS NULL."""
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT txn_id FROM finance_transactions WHERE user_id = $1 AND category IS NULL",
        user_id,
    )
    return [r["txn_id"] for r in rows]


async def fetch_descriptions_for(user_id: UUID, txn_ids: list[str]) -> dict[str, str]:
    """txn_id → description for user_id (may be empty string)."""
    if not txn_ids:
        return {}
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT txn_id, description FROM finance_transactions "
        "WHERE user_id = $1 AND txn_id = ANY($2::text[])",
        user_id, txn_ids,
    )
    return {r["txn_id"]: (r["description"] or "") for r in rows}


async def set_transaction_categories(user_id: UUID, updates: dict[str, str]) -> None:
    """Bulk UPDATE finance_transactions SET category for user_id + txn_id → category mapping."""
    if not updates:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for tid, cat in updates.items():
                await conn.execute(
                    "UPDATE finance_transactions SET category = $1 "
                    "WHERE user_id = $2 AND txn_id = $3",
                    cat, user_id, tid,
                )


async def upsert_category_cache(user_id: UUID, entries: dict[str, str]) -> None:
    """desc_key → category for user_id, idempotent upsert."""
    if not entries:
        return
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            for k, v in entries.items():
                await conn.execute(
                    """
                    INSERT INTO finance_category_cache (user_id, desc_key, category, updated_at)
                    VALUES ($1, $2, $3, now())
                    ON CONFLICT (user_id, desc_key) DO UPDATE
                    SET category = EXCLUDED.category, updated_at = now()
                    """,
                    user_id, k, v,
                )


async def get_category_cache(user_id: UUID, desc_keys: list[str]) -> dict[str, str]:
    """Look up cached categories for user_id + a batch of desc_keys."""
    if not desc_keys:
        return {}
    pool = await get_pool()
    rows = await pool.fetch(
        "SELECT desc_key, category FROM finance_category_cache "
        "WHERE user_id = $1 AND desc_key = ANY($2::text[])",
        user_id, desc_keys,
    )
    return {r["desc_key"]: r["category"] for r in rows}


async def finance_rows_for_month(user_id: UUID, month_str: str) -> list[dict]:
    """Return all rows for user_id for a given calendar month (YYYY-MM), ordered by ts."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT txn_id, ts, direction, amount, currency, description, category
        FROM finance_transactions
        WHERE user_id = $1 AND to_char(ts, 'YYYY-MM') = $2
        ORDER BY ts
        """,
        user_id, month_str,
    )
    return [dict(r) for r in rows]


async def finance_rows_in_window(user_id: UUID, days: int) -> list[dict]:
    """Return rows from (now - `days`) to now for user_id, ordered by ts ASC."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT txn_id, ts, direction, amount, currency, description, category
        FROM finance_transactions
        WHERE user_id = $1 AND ts >= now() - make_interval(days => $2)
        ORDER BY ts
        """,
        user_id, days,
    )
    return [dict(r) for r in rows]


async def finance_rows_all(user_id: UUID) -> list[dict]:
    """Return every row for user_id. Used by current_balance (sum across full history)."""
    pool = await get_pool()
    rows = await pool.fetch(
        """
        SELECT txn_id, ts, direction, amount, currency, description, category
        FROM finance_transactions
        WHERE user_id = $1
        ORDER BY ts
        """,
        user_id,
    )
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Body profile (users.preferences['body_profile'])
# ---------------------------------------------------------------------------

async def get_body_profile(user_id: UUID) -> dict:
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


async def save_body_profile(user_id: UUID, updates: dict) -> None:
    """Merge `updates` into users.preferences['body_profile'].

    Keys with a non-None value are set; keys with None are removed from the
    stored profile (treated as "clear this field").
    """
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
