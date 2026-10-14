import base64

import pytest
from pydantic import ValidationError
from sync.settings import SyncServiceSettings

KEY = base64.b64encode(bytes(range(32))).decode()
DSN = "postgresql+asyncpg://app_rw:pw@localhost/db"


def test_defaults_and_nested_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE__DSN", DSN)
    monkeypatch.setenv("SECRETS__KEY", KEY)
    monkeypatch.setenv("SYNC__HOUR", "8")
    settings = SyncServiceSettings()  # type: ignore[call-arg]
    assert (
        settings.sync.hour,
        settings.sync.interval_minutes,
        settings.sync.manual_cooldown_minutes,
    ) == (8, 15, 10)
    assert settings.sync.yazio_enabled is False
    monkeypatch.setenv("SYNC__YAZIO_CLIENT_ID", "id")
    monkeypatch.setenv("SYNC__YAZIO_CLIENT_SECRET", "secret")
    assert SyncServiceSettings().sync.yazio_enabled is True  # type: ignore[call-arg]


def test_a_missing_key_refuses_to_start(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DATABASE__DSN", DSN)
    monkeypatch.delenv("SECRETS__KEY", raising=False)
    with pytest.raises(ValidationError, match="secrets"):
        SyncServiceSettings(_env_file=None)  # type: ignore[call-arg]
