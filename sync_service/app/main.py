from shared.telemetry import init_telemetry, instrument_fastapi_app
init_telemetry("sync-service")

import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .scheduler import run_daily_sync, start_scheduler
from .sync import do_sync, do_nutrition_sync, do_body_sync

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield


app = FastAPI(title="sync-service", lifespan=lifespan)
instrument_fastapi_app(app)


@app.post("/sync")
async def sync():
    return await do_sync()


@app.post("/sync/nutrition")
async def sync_nutrition():
    return await do_nutrition_sync()


@app.post("/sync/all")
async def sync_all():
    """Run Garmin + Yazio sync and fire the briefing (fire-and-forget)."""
    return await run_daily_sync()


class BodyPayload(BaseModel):
    data: list[dict]


@app.post("/sync/body")
async def sync_body(payload: BodyPayload):
    return await do_body_sync(payload.model_dump())


@app.get("/health")
async def health():
    return {"status": "ok"}
