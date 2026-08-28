"""Tests for orchestrator.app.google_calendar helpers.

Covers token refresh (fresh, expired, revoked-refresh) with mocks around
vault.get/put/delete and the Google token endpoint.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock
from uuid import UUID

import httpx
import pytest

os.environ.setdefault("VAULT_BACKEND", "dev")
os.environ.setdefault("GOOGLE_CALENDAR_OAUTH_CLIENT_ID", "test-client-id")
os.environ.setdefault("GOOGLE_CALENDAR_OAUTH_CLIENT_SECRET", "test-client-secret")
os.environ.setdefault(
    "GOOGLE_CALENDAR_OAUTH_REDIRECT_URI",
    "com.googleusercontent.apps.test-client-id:/integrations-callback",
)

USER = UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb")


def _iso(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


@pytest.mark.asyncio
async def test_fresh_token_returned_as_is(monkeypatch):
    from orchestrator.app import google_calendar as gc
    from orchestrator.app import vault

    future = _iso(datetime.now(timezone.utc) + timedelta(hours=1))
    creds = {"access_token": "FRESH", "refresh_token": "RT", "expires_at": future}
    monkeypatch.setattr(vault, "get", AsyncMock(return_value=creds))

    got = await gc.get_fresh_access_token(USER)
    assert got == "FRESH"


@pytest.mark.asyncio
async def test_expired_token_is_refreshed(monkeypatch):
    from orchestrator.app import google_calendar as gc
    from orchestrator.app import vault

    past = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
    creds = {"access_token": "OLD", "refresh_token": "RT", "expires_at": past}
    stored: dict = {}

    async def fake_put(user_id, service, payload):
        stored.update(payload)

    monkeypatch.setattr(vault, "get", AsyncMock(return_value=creds))
    monkeypatch.setattr(vault, "put", fake_put)
    monkeypatch.setattr(
        gc, "_exchange_refresh_token",
        AsyncMock(return_value={"access_token": "NEW", "expires_in": 3600}),
    )

    got = await gc.get_fresh_access_token(USER)
    assert got == "NEW"
    assert stored["access_token"] == "NEW"
    assert stored["refresh_token"] == "RT"  # preserved


@pytest.mark.asyncio
async def test_revoked_refresh_returns_none_and_deletes(monkeypatch):
    from orchestrator.app import google_calendar as gc
    from orchestrator.app import vault

    past = _iso(datetime.now(timezone.utc) - timedelta(hours=1))
    creds = {"access_token": "OLD", "refresh_token": "BAD", "expires_at": past}
    delete_called = {"n": 0}

    async def fake_delete(user_id, service):
        delete_called["n"] += 1

    monkeypatch.setattr(vault, "get", AsyncMock(return_value=creds))
    monkeypatch.setattr(vault, "delete", fake_delete)
    monkeypatch.setattr(
        gc, "_exchange_refresh_token",
        AsyncMock(side_effect=httpx.HTTPError("400")),
    )

    got = await gc.get_fresh_access_token(USER)
    assert got is None
    assert delete_called["n"] == 1


@pytest.mark.asyncio
async def test_not_connected_returns_none(monkeypatch):
    from orchestrator.app import google_calendar as gc
    from orchestrator.app import vault

    monkeypatch.setattr(vault, "get", AsyncMock(return_value=None))

    got = await gc.get_fresh_access_token(USER)
    assert got is None


def test_build_auth_url_contains_expected_params():
    from orchestrator.app import google_calendar as gc

    url = gc.build_auth_url("STATE123", "CHALLENGE123")
    assert "accounts.google.com" in url
    assert "state=STATE123" in url
    assert "access_type=offline" in url
    assert "response_type=code" in url
    assert (
        "redirect_uri=com.googleusercontent.apps.test-client-id%3A%2Fintegrations-callback"
        in url
    )
    assert "code_challenge=CHALLENGE123" in url
    assert "code_challenge_method=S256" in url


def test_create_pkce_pair_returns_verifier_and_s256_challenge():
    from orchestrator.app import google_calendar as gc

    verifier, challenge = gc.create_pkce_pair()

    assert 43 <= len(verifier) <= 128
    assert challenge
    assert "=" not in challenge
