"""Legacy global HA environment variables must never expose household tools."""

import pytest


@pytest.mark.parametrize(
    "values",
    [
        {},
        {"HA_BASE_URL": "http://ha"},
        {"HA_TOKEN": "token"},
        {"HA_BASE_URL": "http://ha", "HA_TOKEN": "token"},
        {"HA_BASE_URL": "http://ha/", "HA_TOKEN": "token"},
    ],
)
def test_legacy_home_environment_is_ignored(monkeypatch, values):
    from legacy_orchestrator.app import mcp_tools

    for key in ("HA_BASE_URL", "HA_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    for key, value in values.items():
        monkeypatch.setenv(key, value)
    assert mcp_tools._servers_from_env() == {}
