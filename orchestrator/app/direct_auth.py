"""Provider OAuth and application token primitives. No database access."""

from __future__ import annotations

import base64
import hashlib
import os
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any, Literal
from urllib.parse import urlencode
from uuid import UUID

import jwt
from jwt.algorithms import RSAAlgorithm

Provider = Literal["google", "apple"]
ISSUERS = {"google": "https://accounts.google.com", "apple": "https://appleid.apple.com"}
AUTHORIZE = {
    "google": "https://accounts.google.com/o/oauth2/v2/auth",
    "apple": "https://appleid.apple.com/auth/authorize",
}
TOKEN_URL = {
    "google": "https://oauth2.googleapis.com/token",
    "apple": "https://appleid.apple.com/auth/token",
}
JWKS_URL = {
    "google": "https://www.googleapis.com/oauth2/v3/certs",
    "apple": "https://appleid.apple.com/auth/keys",
}


def random_token() -> str:
    return secrets.token_urlsafe(32)


def token_hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def provider_authorization_url(
    provider: Provider, client_id: str, redirect_uri: str, state: str, nonce: str, verifier: str
) -> str:
    challenge = (
        base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    )
    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": "openid profile email" if provider == "google" else "name email",
        "state": state,
        "nonce": nonce,
    }
    if provider == "apple":
        params["response_mode"] = "form_post"
    else:
        params["code_challenge"] = challenge
        params["code_challenge_method"] = "S256"
    return f"{AUTHORIZE[provider]}?{urlencode(params)}"


def decode_provider_identity(
    provider: Provider, id_token: str, client_id: str, nonce: str, jwks: dict[str, Any]
) -> dict[str, str | None]:
    header = jwt.get_unverified_header(id_token)
    key = next(
        (
            k
            for k in jwks.get("keys", [])
            if k.get("kid") == header.get("kid") and k.get("kty") == "RSA"
        ),
        None,
    )
    if key is None:
        raise jwt.InvalidTokenError("unknown provider key")
    claims = jwt.decode(
        id_token,
        RSAAlgorithm.from_jwk(key),
        algorithms=["RS256"],
        audience=client_id,
        issuer=[ISSUERS[provider], "accounts.google.com"]
        if provider == "google"
        else ISSUERS[provider],
        options={"require": ["sub", "exp", "iat", "aud", "iss", "nonce"]},
    )
    if not secrets.compare_digest(str(claims["nonce"]), nonce):
        raise jwt.InvalidTokenError("nonce mismatch")
    if provider == "google" and claims.get("email") and not claims.get("email_verified"):
        raise jwt.InvalidTokenError("email not verified")
    return {"subject": str(claims["sub"]), "email": claims.get("email"), "name": claims.get("name")}


def issue_access(
    user_id: UUID, session_id: UUID, secret: str, *, now: datetime | None = None
) -> str:
    issued = now or datetime.now(UTC)
    return jwt.encode(
        {
            "sub": str(user_id),
            "sid": str(session_id),
            "iss": "lifeagents",
            "aud": "lifeagents",
            "iat": issued,
            "exp": issued + timedelta(minutes=15),
        },
        secret,
        algorithm="HS256",
    )


def decode_access(token: str, secret: str) -> tuple[UUID, UUID]:
    claims = jwt.decode(
        token,
        secret,
        algorithms=["HS256"],
        audience="lifeagents",
        issuer="lifeagents",
        options={"require": ["sub", "sid", "iss", "aud", "iat", "exp"]},
    )
    try:
        return UUID(claims["sub"]), UUID(claims["sid"])
    except (ValueError, TypeError, KeyError) as error:
        raise jwt.InvalidTokenError("malformed subject or session") from error


def app_secret() -> str:
    value = os.environ.get("AUTH_JWT_SECRET", "")
    if len(value) < 32:
        raise RuntimeError("AUTH_JWT_SECRET must contain at least 32 characters")
    return value
