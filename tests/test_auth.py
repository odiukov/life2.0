"""API auth uses our signed, revocable sessions; demo mode remains explicit."""

from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException

from orchestrator.app.direct_auth import issue_access

USER_UUID = "11111111-1111-1111-1111-111111111111"
SECRET = "x" * 32


@pytest.fixture(autouse=True)
def configure(monkeypatch):
    from orchestrator.app import auth

    monkeypatch.setenv("AUTH_JWT_SECRET", SECRET)
    monkeypatch.setattr(auth, "AUTH_MODE", "oauth")


def test_valid_returns_uuid():
    from orchestrator.app.auth import verify_jwt

    assert verify_jwt(f"Bearer {issue_access(UUID(USER_UUID), uuid4(), SECRET)}") == UUID(USER_UUID)


def test_expired_raises_401():
    from datetime import UTC, datetime, timedelta
    from orchestrator.app.auth import verify_jwt

    token = issue_access(
        UUID(USER_UUID), uuid4(), SECRET, now=datetime.now(UTC) - timedelta(hours=1)
    )
    with pytest.raises(HTTPException) as error:
        verify_jwt(f"Bearer {token}")
    assert error.value.status_code == 401


@pytest.mark.parametrize("claim,value", [("aud", "wrong"), ("iss", "evil")])
def test_wrong_claim_raises_401(claim, value):
    from orchestrator.app.auth import verify_jwt

    payload = {
        "sub": USER_UUID,
        "sid": str(uuid4()),
        "aud": "lifeagents",
        "iss": "lifeagents",
        "iat": 1,
        "exp": 9999999999,
    }
    payload[claim] = value
    token = jwt.encode(payload, SECRET, algorithm="HS256")
    with pytest.raises(HTTPException) as error:
        verify_jwt(f"Bearer {token}")
    assert error.value.status_code == 401


def test_missing_bearer_prefix_raises_401():
    from orchestrator.app.auth import verify_jwt

    with pytest.raises(HTTPException) as error:
        verify_jwt("untrusted")
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_dev_mode_reads_x_user_id(monkeypatch):
    from orchestrator.app import auth

    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    assert await auth.current_user(authorization=None, x_user_id=USER_UUID) == UUID(USER_UUID)


@pytest.mark.asyncio
async def test_current_user_dev_mode_rejects_missing_header(monkeypatch):
    from orchestrator.app import auth

    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    with pytest.raises(HTTPException) as error:
        await auth.current_user(authorization=None, x_user_id=None)
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_current_user_dev_mode_rejects_non_uuid(monkeypatch):
    from orchestrator.app import auth

    monkeypatch.setattr(auth, "AUTH_MODE", "dev")
    with pytest.raises(HTTPException) as error:
        await auth.current_user(authorization=None, x_user_id="invalid")
    assert error.value.status_code == 401
