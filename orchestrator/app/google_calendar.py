"""Google OAuth helpers for the per-user calendar integration.

Flow (see spec §4.5.2):
  1. client hits POST /integrations/google_calendar/start → returns auth_url + state
  2. user consents on Google → redirected to the iOS OAuth URL scheme callback
     (for example com.googleusercontent.apps.<client-id>:/integrations-callback?code=&state=)
  3. client POSTs code+state → /integrations/google_calendar/callback → tokens land in vault
  4. calendar-mcp-lite calls carry a fresh access_token (refreshed lazily if expired)

`get_fresh_access_token` is the single entry point every MCP-touching call should use;
it transparently refreshes via refresh_token when the stored access_token is within
REFRESH_SKEW_SECONDS of expiry.
"""
from __future__ import annotations

import os
import base64
import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode
from uuid import UUID

import httpx

from . import vault

CLIENT_ID = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_ID", "")
CLIENT_SECRET = os.environ.get("GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET", "")
REDIRECT_URI = os.environ.get(
    "GOOGLE_CALENDAR_OAUTH_REDIRECT_URI",
    "com.googleusercontent.apps.90325200012-h74926clm7els3i32qjns4vskfurvln1:/integrations-callback",
)

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SCOPES = (
    "https://www.googleapis.com/auth/calendar.events "
    "https://www.googleapis.com/auth/calendar.readonly"
)
REFRESH_SKEW_SECONDS = 60


def is_configured() -> bool:
    return bool(CLIENT_ID)


def create_pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")
    return verifier, challenge


def build_auth_url(state: str, code_challenge: str) -> str:
    """Return Google's OAuth consent URL."""
    params = {
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "scope": SCOPES,
        "response_type": "code",
        "access_type": "offline",
        "prompt": "consent",
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTH_URL}?{urlencode(params)}"


async def _exchange_code(code: str, code_verifier: str) -> dict:
    data = {
        "code": code,
        "client_id": CLIENT_ID,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code",
        "code_verifier": code_verifier,
    }
    if CLIENT_SECRET:
        data["client_secret"] = CLIENT_SECRET
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(TOKEN_URL, data=data)
        r.raise_for_status()
        return r.json()


async def _exchange_refresh_token(refresh_token: str) -> dict:
    data = {
        "refresh_token": refresh_token,
        "client_id": CLIENT_ID,
        "grant_type": "refresh_token",
    }
    if CLIENT_SECRET:
        data["client_secret"] = CLIENT_SECRET
    async with httpx.AsyncClient(timeout=15) as c:
        r = await c.post(TOKEN_URL, data=data)
        r.raise_for_status()
        return r.json()


def _expires_at_iso(expires_in: int) -> str:
    return (
        (datetime.now(timezone.utc) + timedelta(seconds=expires_in))
        .isoformat()
        .replace("+00:00", "Z")
    )


async def store_from_code(user_id: UUID, code: str, code_verifier: str) -> None:
    """Exchange an auth code for tokens and persist them in the vault."""
    tok = await _exchange_code(code, code_verifier)
    await vault.put(
        user_id,
        "google_calendar",
        {
            "access_token": tok["access_token"],
            "refresh_token": tok["refresh_token"],
            "expires_at": _expires_at_iso(int(tok.get("expires_in", 3600))),
        },
    )


async def get_fresh_access_token(user_id: UUID) -> str | None:
    """Return a non-expiring access_token for user_id, refreshing if needed.

    Returns None if the user hasn't connected or if refresh fails — callers treat
    None as "calendar not available" and skip calendar tools gracefully.
    """
    creds = await vault.get(user_id, "google_calendar")
    if not creds:
        return None
    try:
        exp = datetime.fromisoformat(creds["expires_at"].replace("Z", "+00:00"))
    except (KeyError, ValueError):
        exp = datetime.now(timezone.utc)  # force refresh
    if exp > datetime.now(timezone.utc) + timedelta(seconds=REFRESH_SKEW_SECONDS):
        return creds["access_token"]
    # Refresh
    try:
        new = await _exchange_refresh_token(creds["refresh_token"])
    except (httpx.HTTPError, KeyError):
        # refresh_token revoked or invalid; force user to reconnect
        await vault.delete(user_id, "google_calendar")
        return None
    creds["access_token"] = new["access_token"]
    creds["expires_at"] = _expires_at_iso(int(new.get("expires_in", 3600)))
    # Google may or may not rotate refresh_token — preserve prior if absent
    if "refresh_token" in new:
        creds["refresh_token"] = new["refresh_token"]
    await vault.put(user_id, "google_calendar", creds)
    return creds["access_token"]
