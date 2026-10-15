"""/integrations/*: Garmin and Yazio via the sync service, Home Assistant via the home agent,
Google Calendar OAuth (PKCE + signed single-use state) with the code exchanged by the calendar agent.

Errors carry a readable English `detail` (the app shows it in an alert) and a machine `code`.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import secrets
from collections.abc import Callable
from datetime import datetime, timedelta
from typing import Literal, Protocol
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse
from household.adapters.http import Authenticate
from pydantic import BaseModel, Field, SecretStr
from shared.ports.clock import Clock
from shared.ports.credentials import CredentialStore
from shared.ports.skills import SkillCallError, SkillClient, SkillUnavailable
from shared.ports.uow import UnitOfWorkFactory
from shared.schema.tables import health_logs, oauth_state
from shared.skill_ids import Calendar, Home
from sqlalchemy import func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncConnection

from gateway.settings import GatewaySettings
from gateway.validation import PrivateInputRoute

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
SCOPES = "https://www.googleapis.com/auth/calendar.events https://www.googleapis.com/auth/calendar.readonly"
STATE_TTL = timedelta(hours=1)
PREFLIGHT_SOURCES = {"garmin": ["Garmin Connect", "Garmin"], "yazio": ["Yazio"]}
Service = Literal["garmin", "yazio"]
HOME_ERRORS = {
    "invalid_token": (401, "Home Assistant rejected the token."),
    "home_unavailable": (502, "Home Assistant is unreachable from the server."),
    "no_household": (409, "Create or join a family first."),
    "not_connected": (404, "Home Assistant is not connected."),
    "invalid_params": (422, "Check the address (http:// or https://) and the token."),
}


def _error(status: int, code: str, detail: str) -> JSONResponse:
    return JSONResponse({"detail": detail, "code": code}, status_code=status)


class OAuthStateRepository(Protocol):
    async def create(self, user_id: UUID, nonce: UUID, verifier: str) -> None: ...
    async def claim(self, user_id: UUID, nonce: UUID, *, now: datetime) -> str | None:
        """Mark used once; the verifier, or None when unknown, used or older than STATE_TTL."""
        ...


class SourceActivity(Protocol):
    async def summary(
        self, user_id: UUID, sources: list[str], since: datetime
    ) -> tuple[int, datetime | None]: ...


class SqlOAuthStates:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def create(self, user_id: UUID, nonce: UUID, verifier: str) -> None:
        await self._conn.execute(
            insert(oauth_state).values(
                nonce=nonce, user_id=user_id, service="google_calendar", code_verifier=verifier
            )
        )

    async def claim(self, user_id: UUID, nonce: UUID, *, now: datetime) -> str | None:
        c = oauth_state.c
        row = (
            await self._conn.execute(
                update(oauth_state)
                .where(
                    c.nonce == nonce,
                    c.user_id == user_id,
                    c.used_at.is_(None),
                    c.created_at > now - STATE_TTL,
                )
                .values(used_at=now)
                .returning(c.code_verifier)
            )
        ).one_or_none()
        return row.code_verifier if row else None


class SqlSourceActivity:
    def __init__(self, conn: AsyncConnection) -> None:
        self._conn = conn

    async def summary(
        self, user_id: UUID, sources: list[str], since: datetime
    ) -> tuple[int, datetime | None]:
        c = health_logs.c
        row = (
            await self._conn.execute(
                select(func.count(), func.max(c.recorded_at)).where(
                    c.user_id == user_id, c.source.in_(sources), c.recorded_at >= since
                )
            )
        ).one()
        return int(row[0] or 0), row[1]


class HomeStatus(BaseModel):
    connected: bool
    connected_by: str | None = None
    connected_at: str | None = None


class Credentials(BaseModel):
    email: str = Field(min_length=3, max_length=320)
    password: SecretStr = Field(min_length=1, max_length=512)


class HomeConnect(BaseModel):
    base_url: str = Field(pattern=r"^https?://.+", max_length=500)
    token: SecretStr = Field(min_length=8, max_length=4096)


class CalendarCallback(BaseModel):
    code: str = Field(min_length=1, max_length=4096)
    state: str = Field(min_length=1, max_length=200)


def pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode("ascii")).digest())
        .decode("ascii")
        .rstrip("=")
    )
    return verifier, challenge


def build_router(
    settings: GatewaySettings,
    uow: UnitOfWorkFactory,
    clients: Callable[[str], SkillClient],
    http: httpx.AsyncClient,
    authenticate: Authenticate,
    *,
    clock: Clock,
    state_key: bytes | None,
) -> APIRouter:
    router = APIRouter(prefix="/integrations", tags=["integrations"], route_class=PrivateInputRoute)
    user_dependency = Depends(authenticate)

    def sign(user: UUID, nonce: UUID) -> str:
        assert state_key is not None
        return f"{nonce}.{hmac.new(state_key, f'{user}:{nonce}'.encode(), hashlib.sha256).hexdigest()[:32]}"

    def parse(user: UUID, state: str) -> UUID | None:
        if state_key is None:
            return None
        try:
            nonce_text, signature = state.split(".", 1)
            nonce = UUID(nonce_text)
        except ValueError:
            return None
        expected = hmac.new(state_key, f"{user}:{nonce}".encode(), hashlib.sha256).hexdigest()[:32]
        return nonce if hmac.compare_digest(signature.encode(), expected.encode()) else None

    async def home(
        skill: str, user: UUID, params: dict[str, object] | None = None
    ) -> JSONResponse | dict[str, object]:
        try:
            reply = await clients("home").call(skill_id=skill, user_id=user, params=params or {})
        except SkillUnavailable:
            return _error(
                502, "home_agent_unavailable", "The home service is unavailable; try again later."
            )
        except SkillCallError as exc:
            status, detail = HOME_ERRORS.get(exc.code, (502, "Home Assistant returned an error."))
            return _error(status, exc.code, detail)
        return dict(reply.data or {})

    @router.post("/ha/connect", response_model=None)
    async def ha_connect(
        body: HomeConnect, user: UUID = user_dependency
    ) -> JSONResponse | dict[str, object]:
        result = await home(
            Home.CONNECT, user, {"base_url": body.base_url, "token": body.token.get_secret_value()}
        )
        return result if isinstance(result, JSONResponse) else {"status": "connected"}

    @router.post("/ha/test", response_model=None)
    async def ha_test(user: UUID = user_dependency) -> JSONResponse | dict[str, object]:
        return await home(Home.TEST, user)

    @router.post("/ha/disconnect", response_model=None)
    async def ha_disconnect(user: UUID = user_dependency) -> JSONResponse | dict[str, object]:
        result = await home(Home.DISCONNECT, user)
        return result if isinstance(result, JSONResponse) else {"status": "disconnected"}

    @router.get("/ha/status", response_model=HomeStatus)
    async def ha_status(user: UUID = user_dependency) -> JSONResponse | dict[str, object]:
        return await home(Home.STATUS, user)

    @router.post("/google_calendar/start", response_model=None)
    async def gcal_start(user: UUID = user_dependency) -> JSONResponse | dict[str, str]:
        if not settings.google_calendar_oauth_client_id or state_key is None:
            return _error(
                503, "oauth_not_configured", "Google Calendar is not configured on this server."
            )
        nonce = uuid4()
        verifier, challenge = pkce_pair()
        async with uow.for_user(user) as tx:
            await tx.repo(OAuthStateRepository).create(user, nonce, verifier)
        state = sign(user, nonce)
        params = {
            "client_id": settings.google_calendar_oauth_client_id,
            "redirect_uri": settings.google_calendar_oauth_redirect_uri,
            "scope": SCOPES,
            "response_type": "code",
            "access_type": "offline",
            "prompt": "consent",
            "state": state,
            "code_challenge": challenge,
            "code_challenge_method": "S256",
        }
        return {"auth_url": f"{AUTH_URL}?{urlencode(params)}", "state": state}

    @router.post("/google_calendar/callback", response_model=None)
    async def gcal_callback(
        body: CalendarCallback, user: UUID = user_dependency
    ) -> JSONResponse | dict[str, str]:
        nonce = parse(user, body.state)
        if nonce is None:
            return _error(400, "bad_state", "The sign-in link is invalid; start again.")
        async with uow.for_user(user) as tx:
            verifier = await tx.repo(OAuthStateRepository).claim(user, nonce, now=clock.now())
        if verifier is None:
            return _error(
                400, "state_used", "The sign-in link was already used or expired; start again."
            )
        try:
            await clients("calendar").call(
                skill_id=Calendar.CONNECT,
                user_id=user,
                params={"code": body.code, "code_verifier": verifier},
            )
        except SkillUnavailable:
            return _error(
                502,
                "calendar_agent_unavailable",
                "The calendar service is unavailable; try again later.",
            )
        except SkillCallError as exc:
            return _error(400, exc.code, "Google refused the authorization; try again.")
        return {"status": "connected"}

    @router.post("/google_calendar/disconnect", response_model=None)
    async def gcal_disconnect(user: UUID = user_dependency) -> JSONResponse | dict[str, str]:
        try:
            await clients("calendar").call(skill_id=Calendar.DISCONNECT, user_id=user, params={})
        except (SkillUnavailable, SkillCallError):
            return _error(
                502,
                "calendar_agent_unavailable",
                "The calendar service is unavailable; try again later.",
            )
        return {"status": "disconnected"}

    @router.get("/preflight", response_model=None)
    async def preflight(
        service: str = Query(), user: UUID = user_dependency
    ) -> JSONResponse | dict[str, object]:
        sources = PREFLIGHT_SOURCES.get(service)
        if sources is None:
            return _error(422, "unknown_service", f"Unknown service: {service}")
        async with uow.for_user(user) as tx:
            count, last = await tx.repo(SourceActivity).summary(
                user, sources, clock.now() - timedelta(days=7)
            )
        return {
            "detected": count > 0,
            "sample_count": count,
            "last_seen": last.isoformat() if last else None,
        }

    @router.post("/{service}/connect", response_model=None)
    async def connect(
        service: Service, body: Credentials, user: UUID = user_dependency
    ) -> JSONResponse | dict[str, str]:
        password = body.password.get_secret_value()
        try:
            checked = await http.post(
                f"{settings.sync_url.rstrip('/')}/integrations/{service}/test",
                json={"email": body.email, "password": password},
                timeout=20.0,
            )
        except httpx.HTTPError:
            return _error(
                502, "sync_unavailable", "The sync service is unreachable; try again later."
            )
        if checked.status_code != 200:
            try:
                reason = checked.json()
            except ValueError:
                reason = {}
            status = checked.status_code if checked.status_code in (401, 502) else 502
            code = reason.get("code") if isinstance(reason, dict) else None
            details = {
                "auth_failed": "invalid {name} credentials",
                "rate_limited": "{name} is limiting requests; try again later",
                "unavailable": "{name} unreachable",
                "disabled": "{name} sync is not configured on this server",
            }
            if not isinstance(code, str) or code not in details:
                return _error(
                    status, "validation_failed", "Credential validation failed; try again later."
                )
            return _error(
                status,
                code,
                details[code].format(name={"garmin": "Garmin", "yazio": "Yazio"}[service]),
            )
        async with uow.for_user(user) as tx:
            await tx.repo(CredentialStore).put(
                user, service, {"email": body.email, "password": password}
            )
        return {"status": "connected"}

    @router.post("/{service}/disconnect")
    async def disconnect(service: Service, user: UUID = user_dependency) -> dict[str, str]:
        async with uow.for_user(user) as tx:
            await tx.repo(CredentialStore).delete(user, service)
        return {"status": "disconnected"}

    return router
