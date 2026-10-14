import base64

import pytest
from pydantic import SecretStr, ValidationError
from sync.settings import SyncOptions, SyncServiceSettings


def test_sealing_key_is_required_and_validated(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("SECRETS__KEY", raising=False)
    monkeypatch.delenv("SECRETS", raising=False)
    database = {"dsn": "postgresql://unused/unused"}
    with pytest.raises(ValidationError, match="secrets"):
        SyncServiceSettings(database=database)
    with pytest.raises(ValidationError, match="SECRETS__KEY must"):
        SyncServiceSettings(database=database, secrets={"key": "bad"})
    settings = SyncServiceSettings(
        database=database, secrets={"key": base64.b64encode(bytes(32)).decode()}
    )
    assert settings.service_name == "sync-service"
    assert settings.sync.hour == 9


def test_yazio_requires_both_client_secrets() -> None:
    assert not SyncOptions().yazio_enabled
    assert not SyncOptions(yazio_client_id=SecretStr("id")).yazio_enabled
    assert SyncOptions(
        yazio_client_id=SecretStr("id"), yazio_client_secret=SecretStr("secret")
    ).yazio_enabled


@pytest.mark.parametrize(
    "options",
    [
        {"hour": 24},
        {"interval_minutes": 0},
        {"garmin_days": 31},
        {"yazio_days": 0},
        {"manual_cooldown_minutes": -1},
    ],
)
def test_sync_options_validate_bounds(options: dict[str, int]) -> None:
    with pytest.raises(ValidationError):
        SyncOptions.model_validate(options)


@pytest.mark.parametrize(("remaining", "exit_code"), [(0, 0), (1, 1)])
async def test_reencrypt_exit_status_and_count_output(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
    remaining: int,
    exit_code: int,
) -> None:
    from unittest.mock import AsyncMock, MagicMock

    from sync import reencrypt
    from sync.application.reseal import ResealReport

    engine = MagicMock()
    engine.dispose = AsyncMock()
    uow = object()
    monkeypatch.setattr(reencrypt, "create_engine", lambda _database: engine)
    monkeypatch.setattr(reencrypt, "sync_uow", lambda _engine, _box: uow)
    reseal = AsyncMock(return_value=ResealReport(3, remaining))
    monkeypatch.setattr(reencrypt, "reseal_plaintext", reseal)
    settings = SyncServiceSettings(
        database={"dsn": "postgresql://unused/unused"},
        secrets={"key": base64.b64encode(bytes(32)).decode()},
    )
    assert await reencrypt._run(settings) == exit_code
    assert (
        capsys.readouterr().out
        == f"resealed 3 credential rows; {remaining} plaintext rows remain\n"
    )
    reseal.assert_awaited_once_with(uow)
    engine.dispose.assert_awaited_once()
