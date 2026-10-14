from uuid import uuid4

import pytest
from fastapi import HTTPException
from fastapi.exceptions import RequestValidationError


@pytest.mark.asyncio
async def test_revoked_session_rejected(monkeypatch):
    from orchestrator.app import auth
    from orchestrator.app.direct_auth import issue_access

    user, sid = uuid4(), uuid4()
    monkeypatch.setattr(auth, "AUTH_MODE", "oauth")
    monkeypatch.setenv("AUTH_JWT_SECRET", "x" * 32)

    async def inactive(_user, _sid):
        return False

    monkeypatch.setattr(auth, "_session_active", inactive, raising=False)
    with pytest.raises(HTTPException) as error:
        await auth.current_user(
            authorization="Bearer " + issue_access(user, sid, "x" * 32), x_user_id=None
        )
    assert error.value.status_code == 401


@pytest.mark.asyncio
async def test_auth_validation_error_does_not_echo_credentials(caplog):
    from orchestrator.app.main import _log_validation_error

    class Request:
        method = "POST"
        url = type("URL", (), {"path": "/auth/refresh"})()

        async def body(self):
            return b'{"refresh_token":"private-token"}'

    error = RequestValidationError(
        [{"type": "missing", "loc": ("body", "x"), "msg": "Missing", "input": "private-token"}]
    )
    response = await _log_validation_error(Request(), error)
    assert response.status_code == 422
    assert b"private-token" not in response.body
    assert "private-token" not in caplog.text
