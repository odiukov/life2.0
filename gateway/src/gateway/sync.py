"""POST /sync/trigger: start a per-user sync in the background and answer at once."""

from __future__ import annotations

import asyncio
from typing import Any
from uuid import UUID

import httpx
from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from household.adapters.http import Authenticate
from pydantic import AwareDatetime, BaseModel, Field
from shared.observability.logging import get_logger

from gateway.validation import PrivateInputRoute

logger = get_logger(__name__)


class SyncTrigger:
    def __init__(
        self, http: httpx.AsyncClient, sync_url: str, *, concurrency: int, timeout_s: float = 120.0
    ) -> None:
        self._http, self._url, self._timeout = http, sync_url.rstrip("/"), timeout_s
        self._gate = asyncio.Semaphore(concurrency)
        self._tasks: set[asyncio.Task[None]] = set()

    def start(self, user_id: UUID) -> None:
        task = asyncio.create_task(self._run(user_id))
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)

    async def _run(self, user_id: UUID) -> None:
        async with self._gate:
            try:
                response = await self._http.post(
                    f"{self._url}/sync/user", json={"user_id": str(user_id)}, timeout=self._timeout
                )
                response.raise_for_status()
            except Exception as exc:
                logger.warning("sync_trigger_failed", error_type=type(exc).__name__)

    async def drain(self) -> None:
        if self._tasks:
            await asyncio.gather(*list(self._tasks), return_exceptions=True)

    async def aclose(self) -> None:
        for task in list(self._tasks):
            task.cancel()
        await self.drain()


def build_trigger_router(trigger: SyncTrigger, authenticate: Authenticate) -> APIRouter:
    router = APIRouter(tags=["sync"])

    user_dependency = Depends(authenticate)

    @router.post("/sync/trigger", status_code=202)
    async def sync_trigger(user: UUID = user_dependency) -> JSONResponse:
        trigger.start(user)
        return JSONResponse({"ok": True}, status_code=202)

    return router


class HealthSample(BaseModel):
    type: str = Field(max_length=80)
    start: AwareDatetime
    end: AwareDatetime | None = None
    value: float | None = Field(default=None, allow_inf_nan=False)
    unit: str | None = Field(default=None, max_length=100)
    stages: list[dict[str, Any]] | None = Field(default=None, max_length=200)
    source: str | None = Field(default=None, max_length=100)
    activityTypeName: str | None = Field(default=None, max_length=100)


class SyncHealthBody(BaseModel):
    samples: list[HealthSample] = Field(max_length=500)


class HealthSyncResult(BaseModel):
    inserted: int
    received: int
    aggregated: dict[str, int]


def build_health_router(
    http: httpx.AsyncClient, sync_url: str, authenticate: Authenticate
) -> APIRouter:
    router = APIRouter(tags=["sync"], route_class=PrivateInputRoute)
    user_dependency = Depends(authenticate)

    @router.post("/sync/health", response_model=HealthSyncResult)
    async def sync_health(body: SyncHealthBody, user: UUID = user_dependency) -> JSONResponse:
        try:
            response = await http.post(
                f"{sync_url.rstrip('/')}/sync/healthkit",
                json={
                    "user_id": str(user),
                    "samples": [s.model_dump(mode="json", exclude_none=True) for s in body.samples],
                },
                timeout=60.0,
            )
        except httpx.TransportError:
            return JSONResponse({"detail": "sync_unavailable"}, status_code=502)
        if response.status_code >= 500:
            return JSONResponse({"detail": "sync_unavailable"}, status_code=502)
        return JSONResponse(response.json(), status_code=response.status_code)

    return router
