"""Composition root: the only place that chooses adapters."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from shared.adapters.clock import SystemClock
from shared.adapters.db.engine import create_engine
from shared.adapters.scheduler import ApschedulerScheduler
from shared.adapters.secrets import AesGcmSecretBox
from shared.observability.logging import configure_logging
from shared.ports.clock import Clock
from shared.ports.scheduler import Scheduler
from shared.ports.uow import UnitOfWorkFactory
from sqlalchemy.ext.asyncio import AsyncEngine

from sync.adapters.db import sync_uow
from sync.adapters.garmin_client import GarminConnectClient
from sync.adapters.yazio_client import YazioHttpClient
from sync.application.check_credentials import CheckCredentials
from sync.application.ingest_body import IngestBody
from sync.application.ports import GarminClient, YazioClient
from sync.application.sync_due import SyncDue
from sync.application.sync_user import SyncUser
from sync.settings import SyncServiceSettings


@dataclass(frozen=True, slots=True)
class SyncRuntime:
    sync_user: SyncUser
    sync_due: SyncDue
    ingest_body: IngestBody
    check_credentials: CheckCredentials
    scheduler: Scheduler
    engine: AsyncEngine
    uow: UnitOfWorkFactory
    interval_minutes: int


def build_runtime(
    settings: SyncServiceSettings,
    *,
    garmin: GarminClient | None = None,
    yazio: YazioClient | None = None,
    clock: Clock | None = None,
    scheduler: Scheduler | None = None,
) -> SyncRuntime:
    configure_logging(settings.telemetry, private_debug=True)
    options = settings.sync
    engine = create_engine(settings.database)
    uow = sync_uow(engine, AesGcmSecretBox.from_settings(settings.secrets))
    clock = clock if clock is not None else SystemClock()
    garmin = garmin if garmin is not None else GarminConnectClient()
    if yazio is None and options.yazio_client_id and options.yazio_client_secret:
        yazio = YazioHttpClient(
            options.yazio_client_id.get_secret_value(),
            options.yazio_client_secret.get_secret_value(),
            clock=clock,
        )
    sync_user = SyncUser(
        uow=uow,
        garmin=garmin,
        yazio=yazio,
        clock=clock,
        cooldown=timedelta(minutes=options.manual_cooldown_minutes),
        garmin_days=options.garmin_days,
        yazio_days=options.yazio_days,
    )
    return SyncRuntime(
        sync_user=sync_user,
        sync_due=SyncDue(uow=uow, sync_user=sync_user, clock=clock, hour=options.hour),
        ingest_body=IngestBody(uow=uow),
        check_credentials=CheckCredentials(garmin=garmin, yazio=yazio),
        scheduler=scheduler if scheduler is not None else ApschedulerScheduler(),
        engine=engine,
        uow=uow,
        interval_minutes=options.interval_minutes,
    )
