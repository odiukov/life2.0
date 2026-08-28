import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_update_token_executes_jsonb_merge():
    mock_conn = AsyncMock()
    mock_pool = MagicMock()
    mock_pool.acquire.return_value.__aenter__ = AsyncMock(return_value=mock_conn)
    mock_pool.acquire.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("sync_service.app.db.get_pool", new=AsyncMock(return_value=mock_pool)):
        from sync_service.app.db import update_token
        await update_token("user-123", "garmin", "garmin_token", "tok_abc")

    mock_conn.execute.assert_called_once()
    call_args = mock_conn.execute.call_args
    sql = call_args[0][0]
    assert "UPDATE integrations_credentials" in sql
    assert "payload_dev || " in sql
    assert call_args[0][1] == {"garmin_token": "tok_abc"}
    assert call_args[0][2] == "user-123"
    assert call_args[0][3] == "garmin"


@pytest.mark.asyncio
async def test_get_garmin_token_memory_hit():
    import sync_service.app.session as session
    session._garmin_tokens["u1"] = "cached_token"

    result = await session.get_garmin_token("u1")

    assert result == "cached_token"
    session._garmin_tokens.clear()


@pytest.mark.asyncio
async def test_get_garmin_token_db_miss_then_load():
    import sync_service.app.session as session
    session._garmin_tokens.clear()

    with patch(
        "sync_service.app.session.list_user_credentials",
        new=AsyncMock(return_value=[("u2", {"email": "a@b.com", "garmin_token": "db_token"})]),
    ):
        result = await session.get_garmin_token("u2")

    assert result == "db_token"
    assert session._garmin_tokens["u2"] == "db_token"
    session._garmin_tokens.clear()


@pytest.mark.asyncio
async def test_get_garmin_token_db_failure_returns_none():
    import sync_service.app.session as session
    session._garmin_tokens.clear()

    with patch(
        "sync_service.app.session.list_user_credentials",
        new=AsyncMock(side_effect=Exception("db down")),
    ):
        result = await session.get_garmin_token("u3")

    assert result is None


@pytest.mark.asyncio
async def test_save_garmin_token_updates_memory_and_db():
    import sync_service.app.session as session
    session._garmin_tokens.clear()
    mock_update = AsyncMock()

    with patch("sync_service.app.session.update_token", new=mock_update):
        await session.save_garmin_token("u1", "new_token")

    assert session._garmin_tokens["u1"] == "new_token"
    mock_update.assert_called_once_with("u1", "garmin", "garmin_token", "new_token")
    session._garmin_tokens.clear()


@pytest.mark.asyncio
async def test_save_garmin_token_db_failure_does_not_raise():
    import sync_service.app.session as session
    session._garmin_tokens.clear()

    with patch("sync_service.app.session.update_token", new=AsyncMock(side_effect=Exception("db down"))):
        await session.save_garmin_token("u1", "tok")  # must not raise

    assert session._garmin_tokens["u1"] == "tok"
    session._garmin_tokens.clear()


@pytest.mark.asyncio
async def test_get_yazio_token_db_load():
    import sync_service.app.session as session
    session._yazio_tokens.clear()
    stored = {"access_token": "at", "expires_at": "2099-01-01T00:00:00+00:00"}

    with patch(
        "sync_service.app.session.list_user_credentials",
        new=AsyncMock(return_value=[("u4", {"email": "a@b.com", "yazio_token": stored})]),
    ):
        result = await session.get_yazio_token("u4")

    assert result == stored
    session._yazio_tokens.clear()


@pytest.mark.asyncio
async def test_save_yazio_token_updates_memory_and_db():
    import sync_service.app.session as session
    session._yazio_tokens.clear()
    token = {"access_token": "at", "expires_at": "2099-01-01T00:00:00+00:00"}
    mock_update = AsyncMock()

    with patch("sync_service.app.session.update_token", new=mock_update):
        await session.save_yazio_token("u4", token)

    assert session._yazio_tokens["u4"] == token
    mock_update.assert_called_once_with("u4", "yazio", "yazio_token", token)
    session._yazio_tokens.clear()
