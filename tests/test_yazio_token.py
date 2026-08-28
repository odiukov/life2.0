# tests/test_yazio_token.py
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone


def _future_expires_at(seconds: int = 3600) -> str:
    return (datetime.now(timezone.utc) + timedelta(seconds=seconds)).isoformat()


def _past_expires_at() -> str:
    return (datetime.now(timezone.utc) - timedelta(seconds=60)).isoformat()


def test_is_yazio_token_valid_future_expiry():
    from sync_service.app.yazio import is_yazio_token_valid
    token = {"access_token": "at", "expires_at": _future_expires_at(3600)}
    assert is_yazio_token_valid(token) is True


def test_is_yazio_token_valid_expired():
    from sync_service.app.yazio import is_yazio_token_valid
    token = {"access_token": "at", "expires_at": _past_expires_at()}
    assert is_yazio_token_valid(token) is False


def test_is_yazio_token_valid_near_expiry():
    from sync_service.app.yazio import is_yazio_token_valid
    # 2 minutes left — within 5-minute buffer
    token = {"access_token": "at", "expires_at": _future_expires_at(120)}
    assert is_yazio_token_valid(token) is False


def test_is_yazio_token_valid_missing_expires_at():
    from sync_service.app.yazio import is_yazio_token_valid
    assert is_yazio_token_valid({}) is False


@pytest.mark.asyncio
async def test_fetch_diary_reuses_valid_token():
    """Valid token_in → no POST to /oauth/token."""
    from sync_service.app.yazio import fetch_diary

    valid_token = {
        "access_token": "cached_at",
        "expires_at": _future_expires_at(3600),
        "refresh_token": "rt",
    }

    mock_response = MagicMock()
    mock_response.raise_for_status = MagicMock()
    mock_response.json.return_value = {"products": [], "simple_products": [], "recipe_portions": []}

    async def mock_get(url, **kwargs):
        return mock_response

    mock_client = AsyncMock()
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("sync_service.app.yazio.httpx.AsyncClient", return_value=mock_client):
        data, token_out = await fetch_diary(1, "a@b.com", "pass", token_in=valid_token)

    mock_client.post.assert_not_called()
    assert token_out["access_token"] == "cached_at"


@pytest.mark.asyncio
async def test_fetch_diary_uses_refresh_token_when_expired():
    """Expired token with refresh_token → POST with grant_type=refresh_token."""
    from sync_service.app.yazio import fetch_diary

    expired_token = {
        "access_token": "old_at",
        "expires_at": _past_expires_at(),
        "refresh_token": "my_rt",
    }

    auth_response = MagicMock()
    auth_response.raise_for_status = MagicMock()
    auth_response.json.return_value = {
        "access_token": "new_at",
        "expires_in": 3600,
        "refresh_token": "new_rt",
    }

    diary_response = MagicMock()
    diary_response.raise_for_status = MagicMock()
    diary_response.json.return_value = {"products": [], "simple_products": [], "recipe_portions": []}

    post_calls = []

    async def mock_post(url, **kwargs):
        post_calls.append(kwargs.get("json", {}))
        return auth_response

    async def mock_get(url, **kwargs):
        return diary_response

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("sync_service.app.yazio.httpx.AsyncClient", return_value=mock_client):
        data, token_out = await fetch_diary(1, "a@b.com", "pass", token_in=expired_token)

    assert len(post_calls) == 1
    assert post_calls[0]["grant_type"] == "refresh_token"
    assert post_calls[0]["refresh_token"] == "my_rt"
    assert token_out["access_token"] == "new_at"
    assert token_out["refresh_token"] == "new_rt"


@pytest.mark.asyncio
async def test_fetch_diary_falls_back_to_password_when_no_token():
    """No token_in → POST with grant_type=password."""
    from sync_service.app.yazio import fetch_diary

    auth_response = MagicMock()
    auth_response.raise_for_status = MagicMock()
    auth_response.json.return_value = {
        "access_token": "fresh_at",
        "expires_in": 3600,
    }

    diary_response = MagicMock()
    diary_response.raise_for_status = MagicMock()
    diary_response.json.return_value = {"products": [], "simple_products": [], "recipe_portions": []}

    post_calls = []

    async def mock_post(url, **kwargs):
        post_calls.append(kwargs.get("json", {}))
        return auth_response

    async def mock_get(url, **kwargs):
        return diary_response

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("sync_service.app.yazio.httpx.AsyncClient", return_value=mock_client):
        data, token_out = await fetch_diary(1, "a@b.com", "pass", token_in=None)

    assert post_calls[0]["grant_type"] == "password"
    assert token_out["access_token"] == "fresh_at"


@pytest.mark.asyncio
async def test_fetch_diary_falls_back_to_password_when_refresh_fails():
    """Expired token + refresh fails → falls back to password grant."""
    from sync_service.app.yazio import fetch_diary

    expired_token = {
        "access_token": "old_at",
        "expires_at": _past_expires_at(),
        "refresh_token": "bad_rt",
    }

    refresh_error_response = MagicMock()
    refresh_error_response.raise_for_status.side_effect = Exception("401 Unauthorized")

    password_auth_response = MagicMock()
    password_auth_response.raise_for_status = MagicMock()
    password_auth_response.json.return_value = {
        "access_token": "fresh_at",
        "expires_in": 3600,
    }

    diary_response = MagicMock()
    diary_response.raise_for_status = MagicMock()
    diary_response.json.return_value = {"products": [], "simple_products": [], "recipe_portions": []}

    post_calls = []

    async def mock_post(url, **kwargs):
        grant_type = kwargs.get("json", {}).get("grant_type")
        post_calls.append(grant_type)
        if grant_type == "refresh_token":
            return refresh_error_response
        return password_auth_response

    async def mock_get(url, **kwargs):
        return diary_response

    mock_client = AsyncMock()
    mock_client.post = mock_post
    mock_client.get = mock_get
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    with patch("sync_service.app.yazio.httpx.AsyncClient", return_value=mock_client):
        data, token_out = await fetch_diary(1, "a@b.com", "pass", token_in=expired_token)

    assert "refresh_token" in post_calls
    assert "password" in post_calls
    assert token_out["access_token"] == "fresh_at"
