"""FastAPI application. Production starts it through sync.serve."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from shared.observability.logging import get_logger

from sync.adapters.http import build_router
from sync.composition import SyncRuntime, build_runtime
from sync.settings import SyncServiceSettings

logger = get_logger(__name__)


def create_app(runtime: SyncRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(SyncServiceSettings())

    async def due_job() -> None:
        try:
            await built.sync_due()
        except Exception as error:  # e.g. the database is restarting: try again next interval
            logger.warning("sync_due_failed", code="unexpected")
            logger.debug("sync_due_error", error_type=type(error).__name__)

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        built.scheduler.add_interval("sync_due", due_job, minutes=built.interval_minutes)
        await built.scheduler.start()
        try:
            yield
        finally:
            await built.scheduler.shutdown()
            await built.engine.dispose()

    app = FastAPI(title="sync-service", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    app.include_router(
        build_router(
            sync_user=built.sync_user,
            sync_due=built.sync_due,
            ingest_body=built.ingest_body,
            check_credentials=built.check_credentials,
        )
    )
    return app
