"""Tests for the private _servers_from_env() config builder in mcp_tools.

These tests hit a pure function — no async/session mocking — so they stay
deterministic and fast. They lock in the env-var-to-server-config contract
used by MultiServerMCPClient at orchestrator startup.
"""
import importlib


def _fresh_servers(monkeypatch, env: dict[str, str]) -> dict:
    """Reload mcp_tools with a pinned env and return the built server config."""
    # Clear any env we care about, then apply the test's dict.
    for key in ("HA_BASE_URL", "HA_TOKEN"):
        monkeypatch.delenv(key, raising=False)
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    from orchestrator.app import mcp_tools
    importlib.reload(mcp_tools)
    return mcp_tools._servers_from_env()


def test_ha_branch_when_both_env_present(monkeypatch):
    servers = _fresh_servers(monkeypatch, {
        "HA_BASE_URL": "http://homeassistant.local:8123",
        "HA_TOKEN": "tok-abc",
    })
    assert "home-assistant" in servers
    ha = servers["home-assistant"]
    assert ha["url"] == "http://homeassistant.local:8123/mcp_server/sse"
    assert ha["transport"] == "sse"
    assert ha["headers"] == {"Authorization": "Bearer tok-abc"}


def test_ha_skipped_when_token_missing(monkeypatch):
    servers = _fresh_servers(monkeypatch, {
        "HA_BASE_URL": "http://homeassistant.local:8123",
    })
    assert "home-assistant" not in servers


def test_ha_skipped_when_url_missing(monkeypatch):
    servers = _fresh_servers(monkeypatch, {
        "HA_TOKEN": "tok-abc",
    })
    assert "home-assistant" not in servers


def test_ha_skipped_when_both_missing(monkeypatch):
    servers = _fresh_servers(monkeypatch, {})
    assert "home-assistant" not in servers


def test_ha_base_url_trailing_slash_stripped(monkeypatch):
    servers = _fresh_servers(monkeypatch, {
        "HA_BASE_URL": "http://homeassistant.local:8123/",
        "HA_TOKEN": "tok-abc",
    })
    assert servers["home-assistant"]["url"] == "http://homeassistant.local:8123/mcp_server/sse"
