"""Round-trip test for orchestrator.app.vault (dev backend against local postgres)."""
from __future__ import annotations

import os
import pytest
from uuid import UUID

os.environ.setdefault("VAULT_BACKEND", "dev")

import shared.db as _sdb
from orchestrator.app import vault

USER = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")


@pytest.fixture(autouse=True)
async def _pool_and_seed_user():
    if _sdb._pool is not None:
        await _sdb._pool.close()
        _sdb._pool = None
    await _sdb.init_db_pool()
    async with _sdb._pool.acquire() as c:
        await c.execute(
            "INSERT INTO public.users (id, name, timezone) "
            "VALUES ($1, 'vault-test', 'UTC') ON CONFLICT DO NOTHING",
            USER,
        )
    yield
    async with _sdb._pool.acquire() as c:
        await c.execute(
            "DELETE FROM public.integrations_credentials WHERE user_id=$1", USER,
        )
        await c.execute("DELETE FROM public.users WHERE id=$1", USER)
    await _sdb.close_db_pool()


@pytest.mark.asyncio
async def test_put_get_round_trip():
    payload = {"base_url": "https://home.test", "token": "secret-xyz"}
    await vault.put(USER, "ha", payload)
    assert await vault.get(USER, "ha") == payload


@pytest.mark.asyncio
async def test_overwrite_replaces():
    await vault.put(USER, "ha", {"base_url": "https://old", "token": "t1"})
    await vault.put(USER, "ha", {"base_url": "https://new", "token": "t2"})
    got = await vault.get(USER, "ha")
    assert got == {"base_url": "https://new", "token": "t2"}


@pytest.mark.asyncio
async def test_delete_removes():
    await vault.put(USER, "yazio", {"email": "x@y.z", "password": "p"})
    await vault.delete(USER, "yazio")
    assert await vault.get(USER, "yazio") is None


@pytest.mark.asyncio
async def test_get_missing_is_none():
    assert await vault.get(USER, "google_calendar") is None
