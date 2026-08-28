"""Supabase JWT verification.

Public surface:
  - `Depends(current_user) -> UUID` for FastAPI routes
  - `verify_jwt(header_value) -> UUID` for direct/unit-test callers

Two modes, selected by `AUTH_MODE` env var:
  - `supabase` (default): real JWKS verification against SUPABASE_JWKS_URL
  - `dev`: bypass — reads the sub UUID directly from an X-User-Id header.
    Used during local development before the Supabase project lands.
    Never enable in production.
"""
from __future__ import annotations

import json
import os
import time
from typing import Any
from uuid import UUID

import httpx
import jwt
from fastapi import Header, HTTPException
from jwt.algorithms import ECAlgorithm, RSAAlgorithm

AUTH_MODE = os.environ.get("AUTH_MODE", "supabase").lower()
EXPECTED_AUDIENCE = os.environ.get("SUPABASE_JWT_AUDIENCE", "authenticated")
EXPECTED_ISSUER = os.environ.get("SUPABASE_JWT_ISSUER", "")
JWKS_URL = os.environ.get("SUPABASE_JWKS_URL", "")
_JWKS_TTL_SECONDS = 3600

_jwks_cache: dict[str, Any] | None = None
_jwks_fetched_at: float = 0.0


def _fetch_jwks() -> dict:
    """Fetch + cache the Supabase JWKS document. Overridable in tests via monkeypatch."""
    global _jwks_cache, _jwks_fetched_at
    if _jwks_cache and (time.monotonic() - _jwks_fetched_at) < _JWKS_TTL_SECONDS:
        return _jwks_cache
    if not JWKS_URL:
        raise HTTPException(status_code=500, detail="SUPABASE_JWKS_URL not configured")
    with httpx.Client(timeout=5) as c:
        r = c.get(JWKS_URL)
        r.raise_for_status()
        _jwks_cache = r.json()
        _jwks_fetched_at = time.monotonic()
        return _jwks_cache


def _key_for_kid(kid: str):
    """Return a verification key for the given kid.

    Supabase rolls JWT keys with EC (ES256) by default for new projects, so
    we dispatch on `kty`: EC → ECAlgorithm, RSA → RSAAlgorithm.
    """
    jwks = _fetch_jwks()
    for jwk in jwks.get("keys", []):
        if jwk.get("kid") != kid:
            continue
        kty = jwk.get("kty", "").upper()
        jwk_str = json.dumps(jwk)
        if kty == "EC":
            return ECAlgorithm.from_jwk(jwk_str)
        if kty == "RSA":
            return RSAAlgorithm.from_jwk(jwk_str)
        raise HTTPException(status_code=401, detail=f"unsupported key type: {kty}")
    raise HTTPException(status_code=401, detail="unknown key id")


def verify_jwt(authorization: str) -> UUID:
    """Verify a Bearer JWT and return the subject (user_id UUID).

    Raises HTTPException(401) on any failure.
    """
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="missing bearer token")
    token = authorization.removeprefix("Bearer ").strip()
    try:
        unverified = jwt.get_unverified_header(token)
        key = _key_for_kid(unverified.get("kid", ""))
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256", "ES256"],
            audience=EXPECTED_AUDIENCE,
            issuer=EXPECTED_ISSUER,
        )
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="token expired")
    except jwt.InvalidTokenError as e:
        raise HTTPException(status_code=401, detail=f"invalid token: {e.__class__.__name__}")
    sub = claims.get("sub")
    if not sub:
        raise HTTPException(status_code=401, detail="malformed subject")
    try:
        return UUID(sub)
    except ValueError:
        raise HTTPException(status_code=401, detail="malformed subject")


async def current_user(
    authorization: str | None = Header(default=None),
    x_user_id: str | None = Header(default=None, alias="X-User-Id"),
) -> UUID:
    """FastAPI dependency resolving the authenticated user_id.

    AUTH_MODE=supabase (prod): requires Authorization: Bearer <jwt>.
    AUTH_MODE=dev (local): requires X-User-Id: <uuid> header.
    """
    if AUTH_MODE == "dev":
        if not x_user_id:
            raise HTTPException(status_code=401, detail="AUTH_MODE=dev requires X-User-Id header")
        try:
            return UUID(x_user_id)
        except ValueError:
            raise HTTPException(status_code=401, detail="X-User-Id is not a valid UUID")
    if not authorization:
        raise HTTPException(status_code=401, detail="missing Authorization header")
    user_id = verify_jwt(authorization)
    # In the hybrid dev phase our data plane is still local docker postgres,
    # whose per-user tables FK to public.users (instead of auth.users which
    # lives only in Supabase's postgres). Seed public.users on first
    # authenticated hit so FK inserts succeed. Idempotent via ON CONFLICT.
    await _ensure_user_row(user_id)
    return user_id


async def _ensure_user_row(user_id: UUID) -> None:
    # Late import: `shared.db.get_pool` would trigger asyncpg init at module
    # load otherwise, and tests stub the env before it's imported.
    from shared.db import get_pool
    pool = await get_pool()
    async with pool.acquire() as c:
        await c.execute(
            "INSERT INTO public.users (id, name, timezone) "
            "VALUES ($1, $2, 'UTC') ON CONFLICT (id) DO NOTHING",
            user_id, f"supabase:{str(user_id)[:8]}",
        )
