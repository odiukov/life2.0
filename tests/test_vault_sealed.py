"""The credential store seals integration credentials."""

import base64
import json
from uuid import uuid4

import pytest

pytestmark = pytest.mark.integration
KEY = base64.b64encode(bytes(range(32))).decode()


@pytest.fixture(autouse=True)
async def _close_pool_and_reset_box():
    from orchestrator.app import vault
    from shared.db import close_db_pool

    yield
    await close_db_pool()
    vault._reset_box_for_tests()


async def test_put_seals_and_get_reseals_legacy_rows(monkeypatch):
    monkeypatch.setenv("SECRETS__KEY", KEY)
    from orchestrator.app import vault
    from shared.db import get_pool

    vault._reset_box_for_tests()
    pool = await get_pool()
    user = uuid4()
    async with pool.acquire() as c:
        await c.execute("INSERT INTO users (id, name) VALUES ($1, 'u')", user)
    await vault.put(user, "garmin", {"email": "a@b.c", "password": "pw"})
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT payload_dev, payload_enc FROM integrations_credentials WHERE user_id=$1", user
        )
    sealed = bytes(row["payload_enc"])
    assert row["payload_dev"] is None
    assert sealed[0] == 1 and len(sealed) >= 1 + 12 + 16
    assert await vault.get(user, "garmin") == {"email": "a@b.c", "password": "pw"}
    async with pool.acquire() as c:  # a legacy plaintext row
        await c.execute(
            "UPDATE integrations_credentials SET payload_enc = NULL, payload_dev = $2::jsonb WHERE user_id=$1",
            user,
            json.dumps({"email": "a@b.c", "password": "old"}),
        )
    assert (await vault.get(user, "garmin"))["password"] == "old"
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "SELECT payload_dev, payload_enc FROM integrations_credentials WHERE user_id=$1", user
        )
    assert row["payload_dev"] is None and row["payload_enc"] is not None
    async with pool.acquire() as c:
        await c.execute("DELETE FROM users WHERE id=$1", user)


def test_ensure_ready_needs_the_key(monkeypatch):
    from orchestrator.app import vault

    monkeypatch.delenv("SECRETS__KEY", raising=False)
    vault._reset_box_for_tests()
    with pytest.raises(ValueError, match="secrets"):  # pydantic ValidationError is a ValueError
        vault.ensure_ready()
    monkeypatch.setenv("SECRETS__KEY", KEY)
    vault._reset_box_for_tests()
    vault.ensure_ready()
    vault._reset_box_for_tests()


async def test_legacy_resealing_preserves_concurrent_reconnect(monkeypatch):
    import asyncio
    from contextlib import asynccontextmanager

    from orchestrator.app import vault
    from shared.db import get_pool

    monkeypatch.setenv("SECRETS__KEY", KEY)
    pool = await get_pool()
    user = uuid4()
    old = {"password": "old"}
    new = {"password": "new"}
    selected = asyncio.Event()
    resume = asyncio.Event()

    class PausedConnection:
        def __init__(self, connection):
            self.connection = connection

        async def fetchrow(self, *args):
            row = await self.connection.fetchrow(*args)
            selected.set()
            await resume.wait()
            return row

        async def execute(self, *args):
            return await self.connection.execute(*args)

    class PausedPool:
        @asynccontextmanager
        async def acquire(self):
            async with pool.acquire() as connection:
                yield PausedConnection(connection)

    async def paused_pool():
        return PausedPool()

    async with pool.acquire() as connection:
        await connection.execute("INSERT INTO users (id, name) VALUES ($1, 'u')", user)
        await connection.execute(
            "INSERT INTO integrations_credentials (user_id, service, payload_dev) VALUES ($1, 'garmin', $2)",
            user,
            old,
        )
    monkeypatch.setattr(vault, "get_pool", paused_pool)
    read = asyncio.create_task(vault.get(user, "garmin"))
    try:
        await asyncio.wait_for(selected.wait(), timeout=5)
        monkeypatch.setattr(vault, "get_pool", get_pool)
        await vault.put(user, "garmin", new)
        resume.set()
        assert await asyncio.wait_for(read, timeout=5) == old
        assert await vault.get(user, "garmin") == new
    finally:
        resume.set()
        if not read.done():
            read.cancel()
            await asyncio.gather(read, return_exceptions=True)
        async with pool.acquire() as connection:
            await connection.execute("DELETE FROM users WHERE id=$1", user)
