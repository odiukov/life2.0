"""Server-side Google/Apple OAuth and rotating application sessions (ported from auth_routes.py)."""

from __future__ import annotations

import hashlib
import re
from collections.abc import Callable, Coroutine
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import APIRouter, Form, Header, HTTPException, Request, Response
from fastapi.exceptions import RequestValidationError
from fastapi.responses import RedirectResponse
from fastapi.routing import APIRoute
from pydantic import BaseModel
from shared.observability.logging import get_logger
from shared.ports.uow import UnitOfWorkFactory

from gateway.auth.settings import AuthSettings
from gateway.auth.store import AuthStore, Profile
from gateway.auth.tokens import (
    ACCESS_TTL,
    FLOW_TTL,
    JWKS_URL,
    REFRESH_TTL,
    TICKET_TTL,
    TOKEN_URL,
    InvalidRefreshToken,
    Provider,
    apple_client_secret,
    decode_access,
    decode_provider_identity,
    issue_access,
    new_refresh_token,
    parse_refresh_token,
    provider_authorization_url,
    random_token,
    token_hash,
)

logger = get_logger(__name__)
CHALLENGE = re.compile(r"[0-9a-f]{64}")


class AuthRoute(APIRoute):
    """Keep malformed credential inputs out of validation responses and app logs."""

    def get_route_handler(self) -> Callable[[Request], Coroutine[Any, Any, Response]]:
        handle = super().get_route_handler()

        async def validated(request: Request) -> Response:
            try:
                return await handle(request)
            except RequestValidationError:
                raise HTTPException(status_code=422, detail="invalid_auth_request") from None

        return validated


class TicketBody(BaseModel):
    ticket: str
    app_verifier: str


class RefreshBody(BaseModel):
    refresh_token: str


def provider_config(settings: AuthSettings, provider: str) -> tuple[str, str]:
    if provider == "google":
        secret = settings.google_auth_client_secret
        client_id, client_secret = (
            settings.google_auth_client_id,
            secret.get_secret_value() if secret else "",
        )
    elif provider == "apple":
        key = settings.apple_auth_private_key
        client_id = settings.apple_auth_service_id
        client_secret = (
            apple_client_secret(
                team_id=settings.apple_auth_team_id,
                key_id=settings.apple_auth_key_id,
                private_key=key.get_secret_value(),
                client_id=client_id,
            )
            if client_id and key and settings.apple_auth_team_id and settings.apple_auth_key_id
            else ""
        )
    else:
        raise HTTPException(status_code=404, detail="unknown_provider")
    if not client_id or not client_secret:
        raise HTTPException(status_code=503, detail="provider_not_configured")
    return client_id, client_secret


def _public_url(settings: AuthSettings) -> str:
    url = settings.public_url()
    if url is None:
        raise HTTPException(status_code=503, detail="public_url_not_configured")
    return url


def _secret(settings: AuthSettings) -> str:
    secret = settings.secret()
    if secret is None:
        raise HTTPException(status_code=503, detail="auth_not_configured")
    return secret


def _payload(
    settings: AuthSettings, profile: Profile, session: UUID, refresh: str
) -> dict[str, Any]:
    return {
        "access_token": issue_access(profile.user_id, session, _secret(settings)),
        "refresh_token": refresh,
        "expires_at": int((datetime.now(UTC) + ACCESS_TTL).timestamp()),
        "user": {
            "id": str(profile.user_id),
            "email": profile.email,
            "user_metadata": {"full_name": profile.name},
        },
    }


def build_router(
    settings: AuthSettings, uow: UnitOfWorkFactory, http: httpx.AsyncClient
) -> APIRouter:
    router = APIRouter(prefix="/auth", tags=["auth"], route_class=AuthRoute)

    @router.get("/{provider}/start")
    async def start(provider: Provider, app_challenge: str) -> RedirectResponse:
        if not CHALLENGE.fullmatch(app_challenge):
            raise HTTPException(status_code=400, detail="invalid_app_challenge")
        client_id, _ = provider_config(settings, provider)
        callback = f"{_public_url(settings)}/auth/{provider}/callback"
        state, nonce, verifier = random_token(), random_token(), random_token()
        async with uow.system() as tx:
            await tx.repo(AuthStore).begin_flow(
                token_hash(state), provider, verifier, nonce, app_challenge, FLOW_TTL
            )
        return RedirectResponse(
            provider_authorization_url(provider, client_id, callback, state, nonce, verifier)
        )

    async def callback(provider: Provider, state: str, code: str) -> RedirectResponse:
        client_id, client_secret = provider_config(settings, provider)
        redirect_uri = f"{_public_url(settings)}/auth/{provider}/callback"
        async with uow.system() as tx:
            flow = await tx.repo(AuthStore).take_flow(token_hash(state), provider)
        if flow is None:
            raise HTTPException(status_code=401, detail="invalid_oauth_state")
        body = {
            "grant_type": "authorization_code",
            "code": code,
            "client_id": client_id,
            "client_secret": client_secret,
            "redirect_uri": redirect_uri,
        }
        if provider == "google":
            body["code_verifier"] = flow.verifier
        try:
            result = await http.post(TOKEN_URL[provider], data=body, timeout=10.0)
            result.raise_for_status()
            keys = await http.get(JWKS_URL[provider], timeout=10.0)
            keys.raise_for_status()
            identity = decode_provider_identity(
                provider, result.json()["id_token"], client_id, flow.nonce, keys.json()
            )
        except (
            httpx.HTTPError,
            KeyError,
            ValueError,
            TypeError,
            AttributeError,
            jwt.InvalidTokenError,
        ):
            logger.warning("provider_authentication_failed", provider=provider)
            raise HTTPException(status_code=401, detail="provider_authentication_failed") from None
        ticket = random_token()
        async with uow.system() as tx:
            store = tx.repo(AuthStore)
            user = await store.link_identity(
                provider, str(identity["subject"]), identity["email"], identity["name"]
            )
            await store.issue_ticket(token_hash(ticket), user, flow.challenge, TICKET_TTL)
        return RedirectResponse(
            f"{settings.auth_app_redirect_uri}?{urlencode({'ticket': ticket})}", status_code=303
        )

    @router.get("/google/callback")
    async def google_callback(state: str, code: str) -> RedirectResponse:
        return await callback("google", state, code)

    @router.post("/apple/callback")
    async def apple_callback(state: str = Form(), code: str = Form()) -> RedirectResponse:
        return await callback("apple", state, code)

    @router.post("/exchange")
    async def exchange(body: TicketBody) -> dict[str, Any]:
        session = uuid4()
        refresh = new_refresh_token(session)
        async with uow.system() as tx:
            profile = await tx.repo(AuthStore).exchange_ticket(
                token_hash(body.ticket),
                hashlib.sha256(body.app_verifier.encode()).hexdigest(),
                session,
                token_hash(refresh),
                REFRESH_TTL,
            )
        if profile is None:
            raise HTTPException(status_code=401, detail="invalid_ticket")
        return _payload(settings, profile, session, refresh)

    @router.post("/refresh")
    async def refresh(body: RefreshBody) -> dict[str, Any]:
        try:
            session, _ = parse_refresh_token(body.refresh_token)
        except InvalidRefreshToken:
            raise HTTPException(status_code=401, detail="invalid_refresh_token") from None
        rotated = new_refresh_token(session)
        async with uow.system() as tx:  # commits a reuse revocation before the error below
            result = await tx.repo(AuthStore).rotate(
                session, token_hash(body.refresh_token), token_hash(rotated), REFRESH_TTL
            )
        if result.status == "reused":
            raise HTTPException(status_code=401, detail="refresh_token_reused")
        if result.status != "ok" or result.profile is None:
            raise HTTPException(status_code=401, detail="session_expired")
        return _payload(settings, result.profile, session, rotated)

    @router.post("/sign-out", status_code=204)
    async def sign_out(authorization: str | None = Header(default=None)) -> Response:
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="missing_bearer_token")
        try:
            _, session = decode_access(
                authorization.removeprefix("Bearer ").strip(), _secret(settings)
            )
        except jwt.InvalidTokenError:
            raise HTTPException(status_code=401, detail="invalid_token") from None
        async with uow.system() as tx:
            await tx.repo(AuthStore).revoke(session)
        return Response(status_code=204)

    return router
