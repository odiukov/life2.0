"""Server-side Google/Apple OAuth and rotating application sessions."""

from __future__ import annotations

import hashlib
import os
import re
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import UUID, uuid4

import httpx
import jwt
from fastapi import APIRouter, Form, Header, HTTPException
from fastapi.responses import RedirectResponse
from pydantic import BaseModel

from shared.db import get_pool

from .direct_auth import (
    JWKS_URL,
    TOKEN_URL,
    Provider,
    app_secret,
    decode_access,
    decode_provider_identity,
    issue_access,
    provider_authorization_url,
    random_token,
    token_hash,
)

router = APIRouter(prefix="/auth", tags=["auth"])


def provider_config(provider: Provider) -> tuple[str, str]:
    if provider not in ("google", "apple"):
        raise HTTPException(status_code=404, detail="unknown provider")
    if provider == "google":
        client_id = os.environ.get("GOOGLE_AUTH_CLIENT_ID", "")
        secret = os.environ.get("GOOGLE_AUTH_CLIENT_SECRET", "")
    else:
        client_id = os.environ.get("APPLE_AUTH_SERVICE_ID", "")
        secret = apple_client_secret(client_id) if client_id else ""
    if not client_id or not secret:
        raise HTTPException(status_code=503, detail="provider not configured")
    return client_id, secret


def public_url() -> str:
    value = os.environ.get("AUTH_PUBLIC_URL", "").rstrip("/")
    if not value or not (value.startswith("https://") or value.startswith("http://localhost:")):
        raise HTTPException(status_code=503, detail="AUTH_PUBLIC_URL not configured")
    return value


def apple_client_secret(client_id: str) -> str:
    team = os.environ.get("APPLE_AUTH_TEAM_ID", "")
    key_id = os.environ.get("APPLE_AUTH_KEY_ID", "")
    private_key = os.environ.get("APPLE_AUTH_PRIVATE_KEY", "").replace("\\n", "\n")
    if not team or not key_id or not private_key:
        return ""
    now = datetime.now(UTC)
    return jwt.encode(
        {
            "iss": team,
            "iat": now,
            "exp": now + timedelta(days=30),
            "aud": "https://appleid.apple.com",
            "sub": client_id,
        },
        private_key,
        algorithm="ES256",
        headers={"kid": key_id},
    )


def new_refresh_token(session_id: UUID) -> str:
    return f"{session_id}.{random_token()}"


def parse_refresh_token(token: str) -> tuple[UUID, str]:
    try:
        sid_text, secret = token.split(".", 1)
        sid = UUID(sid_text)
        if len(secret) < 32:
            raise ValueError("short token")
        return sid, secret
    except (ValueError, AttributeError) as error:
        raise HTTPException(status_code=401, detail="invalid refresh token") from error


def _payload(
    user_id: UUID, sid: UUID, refresh: str, email: str | None, name: str
) -> dict[str, Any]:
    return {
        "access_token": issue_access(user_id, sid, app_secret()),
        "refresh_token": refresh,
        "expires_at": int((datetime.now(UTC) + timedelta(minutes=15)).timestamp()),
        "user": {"id": str(user_id), "email": email, "user_metadata": {"full_name": name}},
    }


@router.get("/{provider}/start")
async def start(provider: Provider, app_challenge: str):
    if not re.fullmatch(r"[0-9a-f]{64}", app_challenge):
        raise HTTPException(status_code=400, detail="invalid app challenge")
    client_id, _ = provider_config(provider)
    callback = f"{public_url()}/auth/{provider}/callback"
    state, nonce, verifier = random_token(), random_token(), random_token()
    pool = await get_pool()
    await pool.execute(
        "INSERT INTO auth_flows (state_hash, provider, code_verifier, nonce, app_challenge, expires_at) "
        "VALUES ($1, $2, $3, $4, $5, now() + interval '10 minutes')",
        token_hash(state),
        provider,
        verifier,
        nonce,
        app_challenge,
    )
    return RedirectResponse(
        provider_authorization_url(provider, client_id, callback, state, nonce, verifier)
    )


async def _callback(provider: Provider, state: str, code: str):
    client_id, client_secret = provider_config(provider)
    callback = f"{public_url()}/auth/{provider}/callback"
    pool = await get_pool()
    flow = await pool.fetchrow(
        "DELETE FROM auth_flows WHERE state_hash=$1 AND provider=$2 AND expires_at>now() "
        "RETURNING code_verifier, nonce, app_challenge",
        token_hash(state),
        provider,
    )
    if not flow:
        raise HTTPException(status_code=401, detail="invalid or expired OAuth state")
    body = {
        "grant_type": "authorization_code",
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": callback,
    }
    if provider == "google":
        body["code_verifier"] = flow["code_verifier"]
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            result = await client.post(TOKEN_URL[provider], data=body)
            result.raise_for_status()
            id_token = result.json()["id_token"]
            jwks_response = await client.get(JWKS_URL[provider])
            jwks_response.raise_for_status()
            identity = decode_provider_identity(
                provider, id_token, client_id, flow["nonce"], jwks_response.json()
            )
    except (
        httpx.HTTPError,
        KeyError,
        ValueError,
        TypeError,
        AttributeError,
        jwt.InvalidTokenError,
    ) as error:
        raise HTTPException(status_code=401, detail="provider authentication failed") from error
    user_id = await _find_or_create_user(provider, identity)
    ticket = random_token()
    await pool.execute(
        "INSERT INTO auth_tickets (ticket_hash, user_id, app_challenge, expires_at) "
        "VALUES ($1, $2, $3, now() + interval '2 minutes')",
        token_hash(ticket),
        user_id,
        flow["app_challenge"],
    )
    app_redirect = os.environ.get("AUTH_APP_REDIRECT_URI", "lifeagents://auth-callback")
    return RedirectResponse(f"{app_redirect}?{urlencode({'ticket': ticket})}", status_code=303)


async def _find_or_create_user(provider: Provider, identity: dict[str, str | None]) -> UUID:
    pool = await get_pool()
    subject = identity["subject"]
    assert subject is not None
    async with pool.acquire() as conn:
        async with conn.transaction():
            # Serialize first sign-ins for the same provider subject.
            await conn.execute(
                "SELECT pg_advisory_xact_lock(hashtextextended($1, 0))", f"{provider}:{subject}"
            )
            existing = await conn.fetchval(
                "SELECT user_id FROM auth_identities WHERE provider=$1 AND subject=$2",
                provider,
                subject,
            )
            if existing:
                return existing
            user_id = uuid4()
            name = identity["name"] or identity["email"] or provider.title()
            await conn.execute(
                "INSERT INTO users (id, name, timezone) VALUES ($1, $2, 'UTC')", user_id, name
            )
            await conn.execute(
                "INSERT INTO auth_identities (provider, subject, user_id, email) VALUES ($1,$2,$3,$4)",
                provider,
                subject,
                user_id,
                identity["email"],
            )
            return user_id


@router.get("/google/callback")
async def google_callback(state: str, code: str):
    return await _callback("google", state, code)


@router.post("/apple/callback")
async def apple_callback(state: str = Form(), code: str = Form()):
    return await _callback("apple", state, code)


class TicketBody(BaseModel):
    ticket: str
    app_verifier: str


@router.post("/exchange")
async def exchange(body: TicketBody):
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "DELETE FROM auth_tickets WHERE ticket_hash=$1 AND app_challenge=$2 "
                "AND expires_at>now() RETURNING user_id",
                token_hash(body.ticket),
                hashlib.sha256(body.app_verifier.encode()).hexdigest(),
            )
            if not row:
                raise HTTPException(status_code=401, detail="invalid or expired ticket")
            user_id = row["user_id"]
            sid = uuid4()
            refresh = new_refresh_token(sid)
            await conn.execute(
                "INSERT INTO auth_sessions (id, user_id, refresh_hash, expires_at) "
                "VALUES ($1,$2,$3,now() + interval '30 days')",
                sid,
                user_id,
                token_hash(refresh),
            )
            profile = await conn.fetchrow(
                "SELECT u.name, i.email FROM users u JOIN auth_identities i ON i.user_id=u.id "
                "WHERE u.id=$1",
                user_id,
            )
    return _payload(user_id, sid, refresh, profile["email"], profile["name"])


class RefreshBody(BaseModel):
    refresh_token: str


@router.post("/refresh")
async def refresh(body: RefreshBody):
    sid, _ = parse_refresh_token(body.refresh_token)
    pool = await get_pool()
    async with pool.acquire() as conn:
        async with conn.transaction():
            row = await conn.fetchrow(
                "SELECT s.user_id, s.refresh_hash, s.expires_at, s.revoked_at, u.name, i.email "
                "FROM auth_sessions s JOIN users u ON u.id=s.user_id "
                "JOIN auth_identities i ON i.user_id=s.user_id WHERE s.id=$1 FOR UPDATE OF s",
                sid,
            )
            if not row or row["revoked_at"] or row["expires_at"] <= datetime.now(UTC):
                raise HTTPException(status_code=401, detail="session expired")
            if not secrets.compare_digest(row["refresh_hash"], token_hash(body.refresh_token)):
                await conn.execute("UPDATE auth_sessions SET revoked_at=now() WHERE id=$1", sid)
                # Commit the revocation before reporting the failed refresh.
                rejected = True
            else:
                rejected = False
                new_token = new_refresh_token(sid)
                await conn.execute(
                    "UPDATE auth_sessions SET refresh_hash=$2, expires_at=now() + interval '30 days' WHERE id=$1",
                    sid,
                    token_hash(new_token),
                )
        if rejected:
            raise HTTPException(status_code=401, detail="refresh token reused")
    return _payload(row["user_id"], sid, new_token, row["email"], row["name"])


@router.post("/sign-out", status_code=204)
async def sign_out(authorization: str | None = Header(default=None)):
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    try:
        _, sid = decode_access(authorization.removeprefix("Bearer "), app_secret())
    except jwt.InvalidTokenError as error:
        raise HTTPException(status_code=401, detail="invalid token") from error
    pool = await get_pool()
    await pool.execute("UPDATE auth_sessions SET revoked_at=now() WHERE id=$1", sid)
