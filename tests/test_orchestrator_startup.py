"""Credential configuration errors must never include the supplied key in ASGI errors."""

import traceback

import pytest


async def test_vault_startup_configuration_error_is_sanitized(monkeypatch):
    from orchestrator.app import main, vault

    monkeypatch.setenv("SECRETS__KEY", "synthetic-private-orchestrator-key")
    monkeypatch.setattr(vault, "VAULT_BACKEND", "dev")
    monkeypatch.setattr(vault, "_box", None)
    with pytest.raises(Exception) as failure:
        async with main.lifespan(main.app):
            pytest.fail("invalid secrets must prevent startup")
    rendered = "".join(traceback.format_exception(failure.value))
    assert "orchestrator_configuration_invalid" in rendered
    assert "synthetic-private-orchestrator-key" not in rendered
    assert "input_value" not in rendered
    assert "During handling" not in rendered
    assert "direct cause" not in rendered
