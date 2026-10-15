"""API auth uses our signed, revocable sessions; demo mode remains explicit."""

from uuid import UUID, uuid4

import jwt
import pytest
from fastapi import HTTPException
from gateway.auth.authenticate import Authenticator
from gateway.auth.settings import AuthSettings
from gateway.auth.store import AuthStore, InMemoryAuthStore
from gateway.auth.tokens import issue_access
from shared.testing.fakes import InMemoryUnitOfWorkFactory

USER_UUID = "11111111-1111-1111-1111-111111111111"
SECRET = "x" * 32


def authenticator(**kwargs):
    return Authenticator(
        AuthSettings(auth_jwt_secret=SECRET, auth_mode="oauth", session_check=False, **kwargs),
        InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()}),
    )


async def test_valid_returns_uuid():
    verify_jwt = authenticator()

    assert await verify_jwt(f"Bearer {issue_access(UUID(USER_UUID), uuid4(), SECRET)}") == UUID(
        USER_UUID
    )


async def test_expired_raises_401():
    from datetime import UTC, datetime, timedelta

    verify_jwt = authenticator()

    token = issue_access(
        UUID(USER_UUID), uuid4(), SECRET, now=datetime.now(UTC) - timedelta(hours=1)
    )
    with pytest.raises(HTTPException) as error:
        await verify_jwt(f"Bearer {token}")
    assert error.value.status_code == 401


@pytest.mark.parametrize(("claim", "value"), [("aud", "wrong"), ("iss", "evil")])
async def test_wrong_claim_raises_401(claim, value):
    verify_jwt = authenticator()

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
        await verify_jwt(f"Bearer {token}")
    assert error.value.status_code == 401


async def test_missing_bearer_prefix_raises_401():
    verify_jwt = authenticator()

    with pytest.raises(HTTPException) as error:
        await verify_jwt("untrusted")
    assert error.value.status_code == 401


@pytest.mark.parametrize("header", [None, "invalid"])
async def test_dev_rejects_invalid_header(header):
    auth = Authenticator(
        AuthSettings(auth_mode="dev"), InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()})
    )
    with pytest.raises(HTTPException) as error:
        await auth(None, header)
    assert error.value.status_code == 401


async def test_dev_returns_uuid():
    auth = Authenticator(
        AuthSettings(auth_mode="dev"), InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()})
    )
    assert await auth(None, USER_UUID) == UUID(USER_UUID)


async def test_revoked_session_rejected():
    auth = Authenticator(
        AuthSettings(auth_mode="oauth", auth_jwt_secret=SECRET),
        InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()}),
    )
    with pytest.raises(HTTPException) as error:
        await auth("Bearer " + issue_access(UUID(USER_UUID), uuid4(), SECRET), None)
    assert error.value.status_code == 401


async def test_auth_validation_error_does_not_echo_credentials(caplog):
    from datetime import UTC, datetime

    import httpx
    from fastapi import FastAPI
    from household.adapters.http import build_router
    from household.application.service import HouseholdService
    from household.testing import InMemoryHouseholds, in_memory_uow
    from shared.testing.fakes import FixedClock

    clock = FixedClock(datetime.now(UTC))
    auth = Authenticator(
        AuthSettings(auth_mode="dev"), InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()})
    )
    app = FastAPI()
    app.include_router(
        build_router(HouseholdService(in_memory_uow(InMemoryHouseholds(clock)), clock), auth)
    )
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app), base_url="http://test"
    ) as client:
        response = await client.post(
            "/household/join",
            headers={"X-User-Id": USER_UUID, "Authorization": "Bearer private-token"},
            json={},
        )
    assert response.status_code == 422
    assert "private-token" not in response.text
    assert "private-token" not in caplog.text


async def test_malformed_refresh_body_does_not_echo_credentials(caplog):
    import httpx
    from fastapi import FastAPI
    from gateway.auth.routes import build_router

    credential = "synthetic-refresh-credential"
    app = FastAPI()
    async with httpx.AsyncClient() as provider:
        app.include_router(
            build_router(
                AuthSettings(auth_mode="oauth", auth_jwt_secret=SECRET),
                InMemoryUnitOfWorkFactory({AuthStore: InMemoryAuthStore()}),
                provider,
            )
        )
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.post("/auth/refresh", json={"refresh_token": [credential]})
    assert response.status_code == 422
    assert credential not in response.text
    assert credential not in caplog.text
