"""HTTP tests for /integrations/{ha,yazio}/*.

Runs with AUTH_MODE=dev + DEV_FALLBACK_OWNER=false + X-User-Id header
so auth is stable and scoped to a synthetic user.
"""
from __future__ import annotations

import os
import pytest
from uuid import UUID
from httpx import AsyncClient, ASGITransport

os.environ.setdefault("VAULT_BACKEND", "dev")
os.environ.setdefault("AUTH_MODE", "dev")
os.environ["DEV_FALLBACK_OWNER"] = "false"

import shared.db as _sdb

USER = UUID("cccccccc-cccc-cccc-cccc-cccccccccccc")
AUTH_HEADER = {"X-User-Id": str(USER)}


@pytest.fixture(autouse=True)
async def _pool_and_user():
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None
    await _sdb.init_db_pool()
    async with _sdb._pool.acquire() as c:
        await c.execute(
            "INSERT INTO public.users (id, name, timezone) VALUES ($1, 'int-test', 'UTC') ON CONFLICT DO NOTHING",
            USER,
        )
    yield
    async with _sdb._pool.acquire() as c:
        await c.execute("DELETE FROM public.integrations_credentials WHERE user_id=$1", USER)
        await c.execute("DELETE FROM public.users WHERE id=$1", USER)
    await _sdb.close_db_pool()


async def _client():
    # Import app lazily so env vars above are honoured on module load
    from orchestrator.app.main import app
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


@pytest.mark.asyncio
async def test_ha_connect_then_disconnect():
    async with await _client() as c:
        r = await c.post(
            "/integrations/ha/connect",
            json={"base_url": "https://home.test", "token": "longenoughtoken"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200, r.text
        assert r.json() == {"status": "connected"}

        # Test the "test" endpoint — will 502 because home.test isn't reachable;
        # both 200 and 502 are acceptable for this smoke (the endpoint reached
        # the credentials, that's what matters).
        r = await c.post("/integrations/ha/test", headers=AUTH_HEADER)
        assert r.status_code in (200, 502), r.text

        r = await c.post("/integrations/ha/disconnect", headers=AUTH_HEADER)
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_ha_test_without_connect_is_404():
    async with await _client() as c:
        r = await c.post("/integrations/ha/test", headers=AUTH_HEADER)
        assert r.status_code == 404


@pytest.mark.asyncio
async def test_routes_require_auth():
    async with await _client() as c:
        r = await c.post(
            "/integrations/ha/connect",
            json={"base_url": "https://x.test", "token": "longenoughtoken"},
        )
        # AUTH_MODE=dev + DEV_FALLBACK_OWNER=false → 401 without X-User-Id
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_yazio_connect_validates_via_sync_service(monkeypatch):
    from orchestrator.app import integrations_routes

    calls: list[tuple[str, str, str]] = []

    async def fake_validate(service, email, password):
        calls.append((service, email, password))

    monkeypatch.setattr(integrations_routes, "_validate_via_sync_service", fake_validate)

    async with await _client() as c:
        r = await c.post(
            "/integrations/yazio/connect",
            json={"email": "x@y.test", "password": "pw"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 200
        assert calls == [("yazio", "x@y.test", "pw")]
        r = await c.post("/integrations/yazio/disconnect", headers=AUTH_HEADER)
        assert r.status_code == 200


@pytest.mark.asyncio
async def test_yazio_connect_rejects_invalid_credentials(monkeypatch):
    from fastapi import HTTPException

    from orchestrator.app import integrations_routes, vault

    async def fake_validate(service, email, password):
        raise HTTPException(status_code=401, detail="invalid Yazio credentials")

    put_calls: list = []

    async def fake_put(*args, **kwargs):
        put_calls.append((args, kwargs))

    monkeypatch.setattr(integrations_routes, "_validate_via_sync_service", fake_validate)
    monkeypatch.setattr(vault, "put", fake_put)

    async with await _client() as c:
        r = await c.post(
            "/integrations/yazio/connect",
            json={"email": "x@y.test", "password": "wrong"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 401
        assert r.json()["detail"] == "invalid Yazio credentials"
        # creds must NOT be persisted on validation failure
        assert put_calls == []


@pytest.mark.asyncio
async def test_garmin_connect_rejects_invalid_credentials(monkeypatch):
    from fastapi import HTTPException

    from orchestrator.app import integrations_routes, vault

    async def fake_validate(service, email, password):
        raise HTTPException(status_code=401, detail="invalid Garmin credentials")

    put_calls: list = []

    async def fake_put(*args, **kwargs):
        put_calls.append((args, kwargs))

    monkeypatch.setattr(integrations_routes, "_validate_via_sync_service", fake_validate)
    monkeypatch.setattr(vault, "put", fake_put)

    async with await _client() as c:
        r = await c.post(
            "/integrations/garmin/connect",
            json={"email": "x@y.test", "password": "wrong"},
            headers=AUTH_HEADER,
        )
        assert r.status_code == 401
        assert put_calls == []


# -------- Preflight tests --------

@pytest.mark.asyncio
async def test_preflight_garmin_detected_when_recent_samples_exist():
    async with await _client() as c:
        # Seed a recent HealthKit-mirror Garmin sample
        async with _sdb._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO public.health_logs
                  (user_id, agent, type, data, recorded_at, source)
                VALUES ($1, 'workout', 'workout', '{}'::jsonb, now() - interval '1 day', 'Garmin Connect')
                """,
                USER,
            )

        r = await c.get("/integrations/preflight?service=garmin", headers=AUTH_HEADER)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["detected"] is True
        assert body["sample_count"] == 1
        assert body["last_seen"] is not None


@pytest.mark.asyncio
async def test_preflight_garmin_not_detected_when_samples_are_stale():
    async with await _client() as c:
        async with _sdb._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO public.health_logs
                  (user_id, agent, type, data, recorded_at, source)
                VALUES ($1, 'workout', 'workout', '{}'::jsonb, now() - interval '30 days', 'Garmin Connect')
                """,
                USER,
            )

        r = await c.get("/integrations/preflight?service=garmin", headers=AUTH_HEADER)
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["detected"] is False
        assert body["sample_count"] == 0
        assert body["last_seen"] is None


@pytest.mark.asyncio
async def test_preflight_yazio_detects_yazio_source():
    async with await _client() as c:
        async with _sdb._pool.acquire() as conn:
            await conn.execute(
                """
                INSERT INTO public.health_logs
                  (user_id, agent, type, data, recorded_at, source)
                VALUES ($1, 'nutrition', 'dietaryEnergyConsumed', '{}'::jsonb,
                        now() - interval '2 hours', 'Yazio')
                """,
                USER,
            )

        r = await c.get("/integrations/preflight?service=yazio", headers=AUTH_HEADER)
        assert r.status_code == 200
        assert r.json()["detected"] is True


@pytest.mark.asyncio
async def test_preflight_requires_auth():
    async with await _client() as c:
        r = await c.get("/integrations/preflight?service=garmin")
        assert r.status_code == 401


@pytest.mark.asyncio
async def test_preflight_rejects_unknown_service():
    async with await _client() as c:
        r = await c.get("/integrations/preflight?service=oura", headers=AUTH_HEADER)
        assert r.status_code == 422
