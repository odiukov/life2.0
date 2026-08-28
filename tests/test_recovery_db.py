"""Integration test: fetch_recovery_metrics returns the expected per-day dict shape.

Uses the live dev Postgres; inserts synthetic rows and cleans up afterwards.
Skips when POSTGRES_DSN is not set."""
import os
import pytest
import asyncpg
from datetime import datetime, timezone, timedelta
from uuid import UUID


def _has_db():
    return bool(os.environ.get("POSTGRES_DSN"))


pytestmark = pytest.mark.asyncio

# Fixed test user UUID to scope all recovery test rows
_TEST_USER_ID = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")


@pytest.fixture
async def _clean_synthetic_rows():
    """Clean any synthetic test rows before and after each test."""
    async def _clean():
        if not _has_db():
            return
        conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
        try:
            await conn.execute(
                "DELETE FROM health_logs WHERE user_id = $1 AND data->>'source_tag' = 'recovery-test'",
                _TEST_USER_ID,
            )
        finally:
            await conn.close()
    await _clean()
    yield
    await _clean()


@pytest.fixture(autouse=True)
async def _seed_user():
    """Ensure test user exists."""
    if not _has_db():
        yield
        return
    conn = await asyncpg.connect(os.environ["POSTGRES_DSN"])
    try:
        await conn.execute(
            "INSERT INTO public.users (id, name, timezone) VALUES ($1, $2, 'UTC') ON CONFLICT DO NOTHING",
            _TEST_USER_ID, "test-recovery",
        )
    finally:
        await conn.close()
    yield


async def test_fetch_recovery_metrics_joins_sleep_and_daily_stats(_clean_synthetic_rows):
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    dsn = os.environ["POSTGRES_DSN"]

    # Insert synthetic data for "30 days ago" and "31 days ago" — dates far enough
    # in the past that no real garmin data exists, so assertions on None fields hold.
    conn = await asyncpg.connect(dsn)
    try:
        import json
        day1 = datetime.now(timezone.utc) - timedelta(days=30)
        day2 = datetime.now(timezone.utc) - timedelta(days=31)

        await conn.execute(
            "INSERT INTO health_logs (user_id, agent, type, data, recorded_at, source) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6)",
            _TEST_USER_ID, "sleep", "sleep_session",
            json.dumps({"hrv_weekly_avg": 45, "score": 82, "source_tag": "recovery-test"}),
            day1, "garmin-test",
        )
        await conn.execute(
            "INSERT INTO health_logs (user_id, agent, type, data, recorded_at, source) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6)",
            _TEST_USER_ID, "sleep", "daily_stats",
            json.dumps({
                "resting_hr": 58, "stress_avg": 34,
                "body_battery_min": 25, "body_battery_max": 85,
                "source_tag": "recovery-test",
            }),
            day1, "garmin-test",
        )
        await conn.execute(
            "INSERT INTO health_logs (user_id, agent, type, data, recorded_at, source) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6)",
            _TEST_USER_ID, "sleep", "sleep_session",
            json.dumps({"hrv_weekly_avg": 43, "score": 79, "source_tag": "recovery-test"}),
            day2, "garmin-test",
        )
    finally:
        await conn.close()

    from shared.db import fetch_recovery_metrics
    # Pool cache reset (same pattern as habits-registry tests)
    import shared.db as _sdb
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None

    metrics = await fetch_recovery_metrics(_TEST_USER_ID, days=35)
    assert isinstance(metrics, dict)
    assert len(metrics) >= 2  # at least our two synthetic days

    # Find our day1 (30 days ago) and day2 (31 days ago) in the Kyiv-TZ keyed dict.
    from zoneinfo import ZoneInfo
    _tz = ZoneInfo("Europe/Kyiv")
    key1 = day1.astimezone(_tz).date().isoformat()
    key2 = day2.astimezone(_tz).date().isoformat()

    # Our synthetic row for day1 should have all four metrics; day2 only sleep.
    assert metrics[key1]["hrv"] == 45
    assert metrics[key1]["rhr"] == 58
    assert metrics[key1]["stress"] == 34
    assert metrics[key1]["bb_min"] == 25
    assert metrics[key1]["bb_max"] == 85
    assert metrics[key1]["sleep_score"] == 82

    assert metrics[key2]["hrv"] == 43
    # day2 has NO daily_stats row → RHR/stress/bb are None
    assert metrics[key2]["rhr"] is None
    assert metrics[key2]["stress"] is None

    # Close pool so next test gets a fresh one
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


async def test_fetch_recovery_metrics_prefers_hrv_status_over_sleep_dto(_clean_synthetic_rows):
    """When both hrv_status and sleep_session exist for a day, hrv_status.hrv_rmssd
    wins. That's the value the Garmin watch shows; sleep_session.hrv_weekly_avg
    is a different Garmin metric (sleep-window average) that systematically diverges.
    """
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    dsn = os.environ["POSTGRES_DSN"]

    conn = await asyncpg.connect(dsn)
    try:
        import json
        day1 = datetime.now(timezone.utc) - timedelta(days=32)
        # sleep_session says HRV=46 (the buggy value)
        await conn.execute(
            "INSERT INTO health_logs (user_id, agent, type, data, recorded_at, source) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6)",
            _TEST_USER_ID, "sleep", "sleep_session",
            json.dumps({"hrv_weekly_avg": 46, "score": 80, "source_tag": "recovery-test"}),
            day1, "garmin-test",
        )
        # hrv_status says HRV=38 (what the watch shows)
        await conn.execute(
            "INSERT INTO health_logs (user_id, agent, type, data, recorded_at, source) "
            "VALUES ($1, $2, $3, $4::jsonb, $5, $6)",
            _TEST_USER_ID, "sleep", "hrv_status",
            json.dumps({"hrv_rmssd": 38, "status": "BALANCED", "source_tag": "recovery-test"}),
            day1, "garmin-test",
        )
    finally:
        await conn.close()

    from shared.db import fetch_recovery_metrics
    import shared.db as _sdb
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None

    metrics = await fetch_recovery_metrics(_TEST_USER_ID, days=40)

    from zoneinfo import ZoneInfo
    key1 = day1.astimezone(ZoneInfo("Europe/Kyiv")).date().isoformat()
    assert metrics[key1]["hrv"] == 38
    assert metrics[key1]["hrv_sdnn"] == 38

    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None


async def test_fetch_recovery_metrics_empty_when_no_data(_clean_synthetic_rows):
    if not _has_db():
        pytest.skip("POSTGRES_DSN not set")
    # No synthetic rows inserted this test — but the real DB may have other rows.
    # Just check shape: dict with str keys → dict with six numeric-or-None fields.
    from shared.db import fetch_recovery_metrics
    import shared.db as _sdb
    # Reset pool — previous test may have closed it already; just clear the ref
    _sdb._pool = None

    metrics = await fetch_recovery_metrics(_TEST_USER_ID, days=1)
    assert isinstance(metrics, dict)
    for day_key, day_data in metrics.items():
        assert isinstance(day_key, str)
        for field in ("hrv", "rhr", "stress", "bb_min", "bb_max", "sleep_score"):
            assert field in day_data

    # Clean up pool
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None
