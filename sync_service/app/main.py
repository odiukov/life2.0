import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from pydantic import BaseModel

from .scheduler import start_scheduler
from .sync import do_sync, do_nutrition_sync, do_body_sync

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield


app = FastAPI(title="sync-service", lifespan=lifespan)


@app.post("/sync")
async def sync():
    return await do_sync()


@app.post("/sync/nutrition")
async def sync_nutrition():
    return await do_nutrition_sync()


class BodyPayload(BaseModel):
    data: list[dict]


@app.post("/sync/body")
async def sync_body(payload: BodyPayload):
    return await do_body_sync(payload.model_dump())


@app.get("/health")
async def health():
    return {"status": "ok"}
