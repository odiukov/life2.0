from unittest.mock import MagicMock, patch


def _make_garmin_mock(token_out: str = "serialized_token"):
    mock_client = MagicMock()
    mock_client.client.dumps.return_value = token_out

    mock_garmin_cls = MagicMock(return_value=mock_client)
    return mock_garmin_cls, mock_client


def test_fetch_sync_passes_token_in_to_login():
    mock_cls, mock_client = _make_garmin_mock()

    with patch("sync_service.app.garmin.Garmin", mock_cls):
        from sync_service.app.garmin import _fetch_sync
        _fetch_sync(1, "a@b.com", "pass", token_in="existing_token")

    mock_client.login.assert_called_once_with(tokenstore="existing_token")


def test_fetch_sync_passes_none_tokenstore_to_login_when_no_token():
    """When token_in is None, login is called with tokenstore=None (not omitted)."""
    mock_cls, mock_client = _make_garmin_mock()

    with patch("sync_service.app.garmin.Garmin", mock_cls):
        from sync_service.app.garmin import _fetch_sync
        _fetch_sync(1, "a@b.com", "pass", token_in=None)

    mock_client.login.assert_called_once_with(tokenstore=None)


def test_fetch_sync_returns_empty_string_when_dumps_raises():
    mock_client = MagicMock()
    mock_client.client.dumps.side_effect = Exception("serialize error")
    mock_cls = MagicMock(return_value=mock_client)

    with patch("sync_service.app.garmin.Garmin", mock_cls):
        from sync_service.app.garmin import _fetch_sync
        data, token_out = _fetch_sync(1, "a@b.com", "pass", token_in=None)

    assert token_out == ""
    assert "sleep" in data


def test_fetch_sync_returns_token_out():
    mock_cls, mock_client = _make_garmin_mock(token_out="garth_serialized_xyz")

    with patch("sync_service.app.garmin.Garmin", mock_cls):
        from sync_service.app.garmin import _fetch_sync
        data, token_out = _fetch_sync(1, "a@b.com", "pass", token_in=None)

    assert token_out == "garth_serialized_xyz"
    assert "sleep" in data
    assert "activities" in data
