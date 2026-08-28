"""HTTP tests for POST /sync/health (HealthKit ingest)."""
from __future__ import annotations

import os
from uuid import UUID

import pytest
from httpx import ASGITransport, AsyncClient

os.environ.setdefault("AUTH_MODE", "dev")
os.environ["DEV_FALLBACK_OWNER"] = "false"
os.environ.setdefault("VAULT_BACKEND", "dev")

import shared.db as _sdb

USER = UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee")
AUTH_HEADER = {"X-User-Id": str(USER)}


@pytest.fixture(autouse=True)
async def _pool_and_user():
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None
    await _sdb.init_db_pool()
    async with _sdb._pool.acquire() as c:
        await c.execute(
            "INSERT INTO public.users (id, name, timezone) VALUES ($1, 'sync-test', 'UTC') ON CONFLICT DO NOTHING",
            USER,
        )
        await c.execute("DELETE FROM public.health_logs WHERE user_id=$1", USER)
    yield
    async with _sdb._pool.acquire() as c:
        await c.execute("DELETE FROM public.health_logs WHERE user_id=$1", USER)
        await c.execute("DELETE FROM public.users WHERE id=$1", USER)
    await _sdb.close_db_pool()


async def _client():
    from orchestrator.app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


_SAMPLE = {
    "type": "sleep",
    "start": "2026-04-20T23:00:00Z",
    "end": "2026-04-21T07:00:00Z",
    "value": 28800.0,
    "unit": "s",
    "source": "Apple Watch",
}


@pytest.mark.asyncio
async def test_sync_ingests_first_time():
    async with await _client() as c:
        r = await c.post("/sync/health", json={"samples": [_SAMPLE]}, headers=AUTH_HEADER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["inserted"] == 1
    assert body["received"] == 1


@pytest.mark.asyncio
async def test_sync_is_idempotent():
    async with await _client() as c:
        r1 = await c.post("/sync/health", json={"samples": [_SAMPLE]}, headers=AUTH_HEADER)
        r2 = await c.post("/sync/health", json={"samples": [_SAMPLE]}, headers=AUTH_HEADER)
    assert r1.json()["inserted"] == 1
    assert r2.json()["inserted"] == 0   # duplicate suppressed


@pytest.mark.asyncio
async def test_sync_requires_auth():
    async with await _client() as c:
        r = await c.post("/sync/health", json={"samples": [_SAMPLE]})
    assert r.status_code == 401


@pytest.mark.asyncio
async def test_sync_rejects_huge_batch():
    async with await _client() as c:
        huge = {"samples": [_SAMPLE] * 501}
        r = await c.post("/sync/health", json=huge, headers=AUTH_HEADER)
    assert r.status_code == 422  # pydantic validation
