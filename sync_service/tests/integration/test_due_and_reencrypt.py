"""Acceptance 2 and 3 on PostgreSQL: re-sealing plaintext rows and the 09:05 local run."""

import json
from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from shared.adapters.db.engine import create_engine
from shared.adapters.secrets import AesGcmSecretBox
from shared.config import DatabaseSettings
from shared.ports.credentials import CredentialStore
from shared.testing.fakes import FixedClock
from shared.testing.pytest_plugin import PostgresUrls
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine
from sync.adapters.db import sync_uow
from sync.application.reseal import ResealReport, reseal_plaintext
from sync.application.sync_due import DueReport, SyncDue
from sync.application.sync_user import SyncUser
from sync.domain.garmin import GarminBundle
from sync.testing import FakeGarminClient
from sync_fixtures import STATS

pytestmark = pytest.mark.integration
BOX = AesGcmSecretBox(bytes(range(32)))


async def seed(admin: AsyncEngine, tz: str, plaintext: dict[str, dict[str, str]]) -> UUID:
    user = uuid4()
    async with admin.begin() as conn:
        await conn.execute(
            text("INSERT INTO users (id, name, timezone) VALUES (:u, 'u', :tz)"),
            {"u": user, "tz": tz},
        )
        for service, payload in plaintext.items():
            await conn.execute(
                text(
                    "INSERT INTO integrations_credentials (user_id, service, payload_dev) VALUES (:u, :s, CAST(:p AS jsonb))"
                ),
                {"u": user, "s": service, "p": json.dumps(payload)},
            )
    return user


async def test_reencrypt_seals_every_plaintext_row(clean_db: PostgresUrls) -> None:
    admin = create_async_engine(clean_db.admin)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    a = await seed(
        admin,
        "UTC",
        {"garmin": {"email": "a@b.c", "password": "pw"}, "ha": {"url": "u", "token": "t"}},
    )
    await seed(admin, "UTC", {"yazio": {"email": "b@b.c", "password": "pw2"}})
    uow = sync_uow(engine, BOX)
    assert await reseal_plaintext(uow) == ResealReport(resealed=3, remaining=0)
    assert await reseal_plaintext(uow) == ResealReport(resealed=0, remaining=0)
    async with admin.connect() as conn:
        assert (
            await conn.execute(
                text("SELECT count(*) FROM integrations_credentials WHERE payload_dev IS NOT NULL")
            )
        ).scalar_one() == 0
    async with uow.for_user(a) as tx:
        assert await tx.repo(CredentialStore).get(a, "ha") == {"url": "u", "token": "t"}
    await admin.dispose()
    await engine.dispose()


async def test_scheduled_run_at_0905_local_syncs_once(clean_db: PostgresUrls) -> None:
    admin = create_async_engine(clean_db.admin)
    engine = create_engine(DatabaseSettings.model_validate({"dsn": clean_db.rw}))
    user = await seed(admin, "Europe/Lisbon", {"garmin": {"email": "a@b.c", "password": "pw"}})
    clock = FixedClock(datetime(2026, 10, 13, 8, 5, tzinfo=UTC))
    garmin = FakeGarminClient(GarminBundle(stats=((date(2026, 10, 13), STATS),)), token='{"t": 1}')
    uow = sync_uow(engine, BOX)
    sync_user = SyncUser(
        uow=uow, garmin=garmin, yazio=None, clock=clock, cooldown=timedelta(minutes=10)
    )
    due = SyncDue(uow=uow, sync_user=sync_user, clock=clock, hour=9)
    assert await due() == DueReport(1, 0)
    clock.advance(minutes=15)
    assert await due() == DueReport(0, 0)
    async with admin.connect() as conn:
        rows = (
            await conn.execute(
                text("SELECT type, source FROM health_logs WHERE user_id = :u"), {"u": user}
            )
        ).all()
        cred = (
            await conn.execute(
                text("SELECT payload_dev FROM integrations_credentials WHERE user_id = :u"),
                {"u": user},
            )
        ).scalar_one()
    assert [(r.type, r.source) for r in rows] == [("daily_stats", "garmin")]
    assert (
        cred is None
    )  # read once → re-sealed; the refreshed token was merged into the sealed payload
    async with uow.for_user(user) as tx:
        assert (await tx.repo(CredentialStore).get(user, "garmin"))["garmin_token"] == '{"t": 1}'  # type: ignore[index]
    await admin.dispose()
    await engine.dispose()
