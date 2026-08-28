from shared.telemetry import init_telemetry, instrument_fastapi_app
init_telemetry("sync-service")

import logging
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from garminconnect import GarminConnectAuthenticationError, GarminConnectConnectionError
from pydantic import BaseModel

from . import garmin as garmin_client
from . import yazio as yazio_client
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
    """Run Garmin + Yazio sync."""
    return await run_daily_sync()


class BodyPayload(BaseModel):
    data: list[dict]


@app.post("/sync/body")
async def sync_body(payload: BodyPayload):
    return await do_body_sync(payload.model_dump())


class CredentialsPayload(BaseModel):
    email: str
    password: str


@app.post("/integrations/yazio/test")
async def yazio_credentials_test(p: CredentialsPayload):
    """Validate Yazio credentials without persisting anything.

    200 on success, 401 on rejection by Yazio, 502 on transport/upstream errors.
    """
    try:
        await yazio_client.validate_credentials(p.email, p.password)
    except httpx.HTTPStatusError as e:
        if e.response.status_code in (400, 401):
            raise HTTPException(status_code=401, detail="invalid Yazio credentials")
        raise HTTPException(status_code=502, detail=f"Yazio error {e.response.status_code}")
    except httpx.HTTPError as e:
        raise HTTPException(status_code=502, detail=f"Yazio unreachable: {e.__class__.__name__}")
    except ValueError as e:
        raise HTTPException(status_code=502, detail=str(e))
    return {"ok": True}


@app.post("/integrations/garmin/test")
async def garmin_credentials_test(p: CredentialsPayload):
    """Validate Garmin credentials without persisting anything.

    200 on success, 401 on rejection by Garmin, 502 on transport/upstream errors.
    """
    try:
        await garmin_client.validate_credentials(p.email, p.password)
    except GarminConnectAuthenticationError:
        raise HTTPException(status_code=401, detail="invalid Garmin credentials")
    except GarminConnectConnectionError as e:
        raise HTTPException(status_code=502, detail=f"Garmin unreachable: {e}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"Garmin error: {e.__class__.__name__}")
    return {"ok": True}


@app.get("/health")
async def health():
    return {"status": "ok"}
