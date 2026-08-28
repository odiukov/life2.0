"""Integration endpoints for user-provided credentials.

Paths live under `/integrations/{service}/...`. All require auth via
`Depends(current_user)`. Payloads are encrypted at rest via vault.py
(VAULT_BACKEND selects storage backend).

- POST /integrations/ha/{connect,test,disconnect}
- POST /integrations/yazio/{connect,disconnect}

Google Calendar lives in a separate router (Task 16) because its
OAuth-start/callback flow differs.
"""
from __future__ import annotations

import hmac
import hashlib
import os
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from shared.db import get_pool

from . import google_calendar, vault
from .auth import current_user
from .mcp_tools import invalidate_user_mcp_cache

router = APIRouter(prefix="/integrations")

_SYNC_SERVICE_BASE = os.environ.get("SYNC_SERVICE_URL", "http://sync-service:8080")


async def _validate_via_sync_service(service: str, email: str, password: str) -> None:
    """Ask sync-service to verify {service} credentials. Raises HTTPException on failure.

    sync-service owns the third-party clients (garminconnect, yazio httpx);
    keeping validation there avoids duplicating those deps in orchestrator.
    """
    url = f"{_SYNC_SERVICE_BASE}/integrations/{service}/test"
    try:
        async with httpx.AsyncClient(timeout=20.0) as c:
            r = await c.post(url, json={"email": email, "password": password})
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"sync-service unreachable: {e.__class__.__name__}",
        )
    if r.status_code == 200:
        return
    try:
        detail = r.json().get("detail") or f"{service} validation failed"
    except Exception:
        detail = f"{service} validation failed"
    status = r.status_code if r.status_code in (401, 502) else 502
    raise HTTPException(status_code=status, detail=detail)

# HMAC key for OAuth state CSRF protection. Reuses SUPABASE_JWT_SECRET when
# available; falls back to a dev-only fallback string so local tests run
# without a Supabase project.
_STATE_SECRET = os.environ.get(
    "SUPABASE_JWT_SECRET", "dev-state-secret-replace-in-prod"
).encode()


def _sign_state(user_id: UUID, nonce: UUID) -> str:
    msg = f"{user_id}:{nonce}".encode()
    sig = hmac.new(_STATE_SECRET, msg, hashlib.sha256).hexdigest()[:16]
    return f"{nonce}.{sig}"


def _parse_state(user_id: UUID, state: str) -> UUID:
    try:
        nonce_s, sig = state.split(".", 1)
        nonce = UUID(nonce_s)
    except ValueError:
        raise HTTPException(status_code=400, detail="malformed state")
    expected = hmac.new(
        _STATE_SECRET, f"{user_id}:{nonce}".encode(), hashlib.sha256
    ).hexdigest()[:16]
    if not hmac.compare_digest(sig, expected):
        raise HTTPException(status_code=400, detail="bad state signature")
    return nonce


class HAPayload(BaseModel):
    base_url: str = Field(..., pattern=r"^https?://.+")
    token: str = Field(..., min_length=8)


class YazioPayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


class GarminPayload(BaseModel):
    email: str = Field(..., min_length=3)
    password: str = Field(..., min_length=1)


# -------- Home Assistant --------

@router.post("/ha/connect")
async def ha_connect(p: HAPayload, user_id: UUID = Depends(current_user)):
    await vault.put(user_id, "ha", p.model_dump())
    invalidate_user_mcp_cache(user_id)
    return {"status": "connected"}


@router.post("/ha/test")
async def ha_test(user_id: UUID = Depends(current_user)):
    creds = await vault.get(user_id, "ha")
    if not creds:
        raise HTTPException(status_code=404, detail="ha not connected")
    url = creds["base_url"].rstrip("/") + "/api/"
    try:
        async with httpx.AsyncClient(timeout=5) as c:
            r = await c.get(url, headers={"Authorization": f"Bearer {creds['token']}"})
            r.raise_for_status()
            return {"status": "ok", "ha_version": r.json().get("version")}
    except httpx.HTTPError as e:
        raise HTTPException(
            status_code=502,
            detail=f"ha unreachable: {e.__class__.__name__}",
        )


@router.post("/ha/disconnect")
async def ha_disconnect(user_id: UUID = Depends(current_user)):
    await vault.delete(user_id, "ha")
    invalidate_user_mcp_cache(user_id)
    return {"status": "disconnected"}


# -------- Yazio (opt-in BYOC) --------

@router.post("/yazio/connect")
async def yazio_connect(p: YazioPayload, user_id: UUID = Depends(current_user)):
    await _validate_via_sync_service("yazio", p.email, p.password)
    await vault.put(user_id, "yazio", p.model_dump())
    return {"status": "connected"}


@router.post("/yazio/disconnect")
async def yazio_disconnect(user_id: UUID = Depends(current_user)):
    await vault.delete(user_id, "yazio")
    return {"status": "disconnected"}


# -------- Garmin Connect (BYOC) --------

@router.post("/garmin/connect")
async def garmin_connect(p: GarminPayload, user_id: UUID = Depends(current_user)):
    await _validate_via_sync_service("garmin", p.email, p.password)
    await vault.put(user_id, "garmin", p.model_dump())
    return {"status": "connected"}


@router.post("/garmin/disconnect")
async def garmin_disconnect(user_id: UUID = Depends(current_user)):
    await vault.delete(user_id, "garmin")
    return {"status": "disconnected"}


# -------- Google Calendar (OAuth) --------

class GCalCallback(BaseModel):
    code: str
    state: str


@router.post("/google_calendar/start")
async def gcal_start(user_id: UUID = Depends(current_user)):
    if not google_calendar.is_configured():
        raise HTTPException(
            status_code=503,
            detail="Google Calendar OAuth is not configured. Set GOOGLE_CALENDAR_OAUTH_CLIENT_ID.",
        )
    nonce = uuid4()
    state = _sign_state(user_id, nonce)
    code_verifier, code_challenge = google_calendar.create_pkce_pair()
    pool = await get_pool()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO oauth_state (nonce, user_id, service, code_verifier) "
            "VALUES ($1, $2, 'google_calendar', $3)",
            nonce, user_id, code_verifier,
        )
    return {"auth_url": google_calendar.build_auth_url(state, code_challenge), "state": state}


@router.post("/google_calendar/callback")
async def gcal_callback(p: GCalCallback, user_id: UUID = Depends(current_user)):
    nonce = _parse_state(user_id, p.state)
    pool = await get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow(
            "UPDATE oauth_state SET used_at=now() "
            "WHERE nonce=$1 AND user_id=$2 AND used_at IS NULL "
            "RETURNING code_verifier",
            nonce, user_id,
        )
        if row is None:
            raise HTTPException(status_code=400, detail="state already used or unknown")
    await google_calendar.store_from_code(user_id, p.code, row["code_verifier"])
    return {"status": "connected"}


@router.post("/google_calendar/disconnect")
async def gcal_disconnect(user_id: UUID = Depends(current_user)):
    await vault.delete(user_id, "google_calendar")
    return {"status": "disconnected"}


# -------- Preflight (advisory) --------

# Map service name → HealthKit-mirror source values to look for in health_logs.
# These names come from sourceRevision.source.name on iOS samples.
_PREFLIGHT_SOURCES: dict[str, list[str]] = {
    "garmin": ["Garmin Connect", "Garmin"],
    "yazio": ["Yazio"],
}


@router.get("/preflight")
async def preflight(
    service: str,
    user_id: UUID = Depends(current_user),
):
    """Check whether {service} data is already flowing in via Apple Health.

    Advisory only — used by mobile panels to surface a "you may not need this"
    banner when the user opens Garmin/Yazio direct-connect screens.
    """
    sources = _PREFLIGHT_SOURCES.get(service)
    if sources is None:
        raise HTTPException(status_code=422, detail=f"unknown service: {service}")

    pool = await get_pool()
    async with pool.acquire() as c:
        row = await c.fetchrow(
            """
            SELECT COUNT(*) AS sample_count, MAX(recorded_at) AS last_seen
              FROM health_logs
             WHERE user_id = $1
               AND source = ANY($2::text[])
               AND recorded_at >= now() - interval '7 days'
            """,
            user_id,
            sources,
        )

    sample_count = int(row["sample_count"] or 0)
    last_seen = row["last_seen"]
    return {
        "detected": sample_count > 0,
        "sample_count": sample_count,
        "last_seen": last_seen.isoformat() if last_seen else None,
    }
