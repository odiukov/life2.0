"""Unit tests for orchestrator.app.auth.verify_jwt + current_user."""
from __future__ import annotations

import pytest
from fastapi import HTTPException
from uuid import UUID

from tests.fixtures.jwt_factory import build, jwks, ISSUER


@pytest.fixture(autouse=True)
def patch_jwks_and_issuer(monkeypatch):
    """Stub JWKS fetch and EXPECTED_ISSUER for every test."""
    from orchestrator.app import auth

    _STATIC_JWKS = jwks()
    monkeypatch.setattr(auth, "_fetch_jwks", lambda: _STATIC_JWKS)
    monkeypatch.setattr(auth, "EXPECTED_ISSUER", ISSUER)
    monkeypatch.setattr(auth, "AUTH_MODE", "supabase")
    # Reset the module-level JWKS cache so other tests can't leak a stale one
    monkeypatch.setattr(auth, "_jwks_cache", None)


USER_UUID = "11111111-1111-1111-1111-111111111111"


def test_valid_returns_uuid():
    from orchestrator.app.auth import verify_jwt
    token = build(USER_UUID)
    assert verify_jwt(f"Bearer {token}") == UUID(USER_UUID)


def test_expired_raises_401():
    from orchestrator.app.auth import verify_jwt
    token = build(USER_UUID, ttl=-60)
    with pytest.raises(HTTPException) as exc:
        verify_jwt(f"Bearer {token}")
    assert exc.value.status_code == 401
    assert "expired" in exc.value.detail.lower()


def test_wrong_audience_raises_401():
    from orchestrator.app.auth import verify_jwt
    token = build(USER_UUID, aud="wrong")
    with pytest.raises(HTTPException) as exc:
        verify_jwt(f"Bearer {token}")
    assert exc.value.status_code == 401


def test_wrong_issuer_raises_401():
    from orchestrator.app.auth import verify_jwt
    token = build(USER_UUID, iss="https://evil.example.com/auth/v1")
    with pytest.raises(HTTPException) as exc:
        verify_jwt(f"Bearer {token}")
    assert exc.value.status_code == 401


def test_missing_bearer_prefix_raises_401():
    from orchestrator.app.auth import verify_jwt
    token = build(USER_UUID)
    with pytest.raises(HTTPException) as exc:
        verify_jwt(token)  # no "Bearer " prefix
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_dev_mode_reads_x_user_id(monkeypatch):
    from orchestrator.app import auth
    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    got = await auth.current_user(authorization=None, x_user_id=USER_UUID)
    assert got == UUID(USER_UUID)


@pytest.mark.asyncio
async def test_current_user_dev_mode_rejects_missing_header(monkeypatch):
    from orchestrator.app import auth
    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    with pytest.raises(HTTPException) as exc:
        await auth.current_user(authorization=None, x_user_id=None)
    assert exc.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_dev_mode_rejects_non_uuid(monkeypatch):
    from orchestrator.app import auth
    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    with pytest.raises(HTTPException) as exc:
        await auth.current_user(authorization=None, x_user_id="not-a-uuid")
    assert exc.value.status_code == 401
