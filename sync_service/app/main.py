import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI

from .scheduler import start_scheduler
from .sync import do_sync

logging.basicConfig(level=logging.INFO)


@asynccontextmanager
async def lifespan(app: FastAPI):
    start_scheduler()
    yield


app = FastAPI(title="sync-service", lifespan=lifespan)


@app.post("/sync")
async def sync():
    return await do_sync()


@app.get("/health")
async def health():
    return {"status": "ok"}
