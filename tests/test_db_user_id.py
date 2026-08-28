"""User-scoping isolation test for shared.db."""
import pytest
import shared.db as _sdb
from uuid import UUID
from datetime import datetime, timezone
from shared.db import (
    insert_health_log, fetch_health_logs,
    init_db_pool, close_db_pool,
)

USER_A = UUID("11111111-1111-1111-1111-111111111111")
USER_B = UUID("22222222-2222-2222-2222-222222222222")


@pytest.fixture(autouse=True)
async def _pool_and_seed_users():
    # Reset any existing pool so we get a fresh one on this loop.
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None

    await init_db_pool()
    async with _sdb._pool.acquire() as c:
        for uid in (USER_A, USER_B):
            await c.execute(
                "INSERT INTO public.users (id, name, timezone) VALUES ($1, $2, 'UTC') ON CONFLICT DO NOTHING",
                uid, f"test-{str(uid)[:8]}",
            )
    yield
    async with _sdb._pool.acquire() as c:
        await c.execute("DELETE FROM public.health_logs WHERE user_id = ANY($1)", [USER_A, USER_B])
        await c.execute("DELETE FROM public.users WHERE id = ANY($1)", [USER_A, USER_B])
    await close_db_pool()


@pytest.mark.asyncio
async def test_cross_user_isolation():
    now = datetime.now(timezone.utc)
    await insert_health_log(USER_A, "test_sleep", now, {"tag": "a-only"})
    await insert_health_log(USER_B, "test_sleep", now, {"tag": "b-only"})
    a_rows = await fetch_health_logs(USER_A, "test_sleep", limit=10)
    b_rows = await fetch_health_logs(USER_B, "test_sleep", limit=10)
    a_tags = [r["data"]["tag"] for r in a_rows]
    b_tags = [r["data"]["tag"] for r in b_rows]
    assert "a-only" in a_tags and "b-only" not in a_tags
    assert "b-only" in b_tags and "a-only" not in b_tags
