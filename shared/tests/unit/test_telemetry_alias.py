import pytest
import shared.telemetry as legacy
from shared.observability import telemetry


def test_legacy_global_patch_affects_new_module(monkeypatch: pytest.MonkeyPatch) -> None:
    assert legacy is telemetry
    monkeypatch.setattr(legacy, "_INITIALIZED", False)
    monkeypatch.setenv("TELEMETRY_ENABLED", "false")
    telemetry.init_telemetry("alias-test")
    assert legacy._INITIALIZED is True
