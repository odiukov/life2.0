"""Internal HTTP API of the sync service (reachable only on the compose network)."""

from __future__ import annotations

from dataclasses import asdict
from uuid import UUID

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field, SecretStr
from shared.observability.logging import get_logger

from sync.application.check_credentials import CheckCredentials
from sync.application.ingest_body import IngestBody
from sync.application.ports import SERVICES, Credentials, Service
from sync.application.sync_due import SyncDue
from sync.application.sync_user import SyncUser

logger = get_logger(__name__)

_NAMES = {"garmin": "Garmin", "yazio": "Yazio"}
_DETAILS = {
    "auth_failed": "invalid {name} credentials",
    "rate_limited": "{name} is limiting requests; try again later",
    "unavailable": "{name} unreachable",
    "disabled": "{name} sync is not configured on this server",
}


class SyncUserRequest(BaseModel):
    user_id: UUID
    services: list[Service] | None = Field(default=None, min_length=1)


class BodyEntry(BaseModel):
    name: str = Field(max_length=100)
    date: str = Field(max_length=40)
    qty: float | None = None
    units: str | None = Field(default=None, max_length=20)


class BodyRequest(BaseModel):
    user_id: UUID
    data: list[BodyEntry] = Field(max_length=5000)


class CredentialsRequest(BaseModel):
    email: str = Field(min_length=1, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=512)


def build_router(
    *,
    sync_user: SyncUser,
    sync_due: SyncDue,
    ingest_body: IngestBody,
    check_credentials: CheckCredentials,
) -> APIRouter:
    router = APIRouter()

    @router.post("/sync/user")
    async def sync_one(request: SyncUserRequest) -> dict[str, object]:
        results = await sync_user(request.user_id, request.services or SERVICES)
        return {"user_id": str(request.user_id), "results": [asdict(r) for r in results]}

    @router.post("/sync/all", deprecated=True)
    async def sync_all() -> dict[str, int]:
        logger.warning("sync_all_deprecated")
        report = await sync_due(force=True)
        return {"users": report.users, "failed": report.failed}

    @router.post("/sync/body")
    async def sync_body(request: BodyRequest) -> dict[str, int]:
        result = await ingest_body(request.user_id, [entry.model_dump() for entry in request.data])
        return {"written": result.written, "unchanged": result.unchanged}

    @router.post("/integrations/{service}/test", response_model=None)
    async def test_credentials(
        service: str, request: CredentialsRequest
    ) -> dict[str, bool] | JSONResponse:
        if service not in SERVICES:
            return JSONResponse({"detail": "unknown service"}, status_code=404)
        status = await check_credentials(
            service, Credentials(request.email, request.password.get_secret_value())
        )
        if status == "ok":
            return {"ok": True}
        detail = _DETAILS[status].format(name=_NAMES[service])
        return JSONResponse(
            {"detail": detail, "code": status}, status_code=401 if status == "auth_failed" else 502
        )

    return router
