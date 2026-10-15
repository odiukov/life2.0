"""HealthKit ingestion uses the real tenant repository and preserves rollup keys."""

import base64
from uuid import uuid4

import httpx
import pytest
from shared.ports.health_logs import HealthLogRepository
from shared.testing.fakes import FakeScheduler
from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sync.composition import build_runtime
from sync.main import create_app
from sync.settings import SyncServiceSettings

pytestmark = pytest.mark.integration


async def test_healthkit_http_persists_rollups_idempotently_and_isolates_users(clean_db):
    user, other = uuid4(), uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        for uid in (user, other):
            await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": uid})
    runtime = build_runtime(
        SyncServiceSettings.model_validate(
            {
                "database": {"dsn": clean_db.rw},
                "secrets": {"key": base64.b64encode(bytes(range(32))).decode()},
            }
        ),
        scheduler=FakeScheduler(),
    )
    app = create_app(runtime)
    samples = [
        {
            "type": "sleepAnalysis",
            "start": "2026-10-13T22:00:00Z",
            "end": "2026-10-14T04:00:00Z",
            "value": 3,
            "source": "Fitness",
        },
        {"type": "stepCount", "start": "2026-10-13T09:00:00Z", "value": 5000, "source": "Fitness"},
        {"type": "stepCount", "start": "2026-10-13T09:00:00Z", "value": 9000, "source": "iPhone"},
        {"type": "dietaryEnergyConsumed", "start": "2026-10-13T09:00:00Z", "value": 1800},
    ]
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://sync"
            ) as client,
        ):
            body = {"user_id": str(user), "samples": samples}
            first = await client.post("/sync/healthkit", json=body)
            assert first.status_code == 200
            assert first.json() == {
                "inserted": 4,
                "received": 4,
                "aggregated": {
                    "sleep_sessions": 1,
                    "daily_stats": 1,
                    "workouts": 0,
                    "nutrition_days": 1,
                },
            }
            async with admin.connect() as conn:
                rows = (
                    await conn.execute(
                        text("SELECT type, source, data FROM health_logs WHERE user_id=:u"),
                        {"u": user},
                    )
                ).all()
            rollups = {r.type: r for r in rows}
            assert len(rows) == 7
            assert rollups["sleep_session"].source == "HealthKit"
            assert rollups["sleep_session"].data["duration_seconds"] == 21600
            assert rollups["daily_stats"].data["stepCount"] == 5000
            assert rollups["meal"].source == "apple_health"
            second = await client.post("/sync/healthkit", json=body)
            assert second.json()["inserted"] == 0
            async with admin.connect() as conn:
                assert (
                    await conn.execute(
                        text("SELECT count(*) FROM health_logs WHERE user_id=:u"), {"u": user}
                    )
                ).scalar_one() == 7
            empty = await client.post(
                "/sync/healthkit", json={"user_id": str(other), "samples": []}
            )
            assert not any(empty.json()["aggregated"].values())
            async with runtime.uow.for_user(other) as tx:
                assert (
                    await tx.repo(HealthLogRepository).recent(
                        user, types=["sleep_session", "daily_stats", "meal"]
                    )
                    == []
                )
    finally:
        await admin.dispose()


async def test_concurrent_chunks_leave_complete_aggregate(clean_db, monkeypatch):
    import asyncio

    from shared.adapters.db.health_logs import SqlHealthLogs

    user = uuid4()
    admin = create_async_engine(clean_db.admin)
    async with admin.begin() as conn:
        await conn.execute(text("INSERT INTO users (id, name) VALUES (:u, 'u')"), {"u": user})
    runtime = build_runtime(
        SyncServiceSettings.model_validate(
            {
                "database": {"dsn": clean_db.rw},
                "secrets": {"key": base64.b64encode(bytes(range(32))).decode()},
            }
        ),
        scheduler=FakeScheduler(),
    )
    first_read, release = asyncio.Event(), asyncio.Event()
    original = SqlHealthLogs.recent
    calls = 0

    async def pause_first_read(self, *args, **kwargs):
        nonlocal calls
        rows = await original(self, *args, **kwargs)
        calls += 1
        if calls == 1:
            first_read.set()
            await release.wait()
        return rows

    monkeypatch.setattr(SqlHealthLogs, "recent", pause_first_read)
    app = create_app(runtime)
    try:
        async with (
            app.router.lifespan_context(app),
            httpx.AsyncClient(
                transport=httpx.ASGITransport(app=app), base_url="http://sync"
            ) as client,
        ):
            first = asyncio.create_task(
                client.post(
                    "/sync/healthkit",
                    json={
                        "user_id": str(user),
                        "samples": [
                            {"type": "stepCount", "start": "2026-10-13T09:00:00Z", "value": 100}
                        ],
                    },
                )
            )
            await asyncio.wait_for(first_read.wait(), timeout=5)
            second = asyncio.create_task(
                client.post(
                    "/sync/healthkit",
                    json={
                        "user_id": str(user),
                        "samples": [
                            {"type": "stepCount", "start": "2026-10-13T10:00:00Z", "value": 200}
                        ],
                    },
                )
            )
            try:
                await asyncio.wait_for(asyncio.shield(second), timeout=1)
            except TimeoutError:
                pass
            finally:
                release.set()
            responses = await asyncio.gather(first, second)
            assert [r.status_code for r in responses] == [200, 200]
            async with admin.connect() as conn:
                totals = (
                    (
                        await conn.execute(
                            text(
                                "SELECT data FROM health_logs WHERE user_id=:u AND type='daily_stats'"
                            ),
                            {"u": user},
                        )
                    )
                    .scalars()
                    .all()
                )
            assert totals == [{"stepCount": 300}]
    finally:
        release.set()
        await admin.dispose()
