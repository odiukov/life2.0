"""Invalid deployment settings fail closed without writing secrets to stderr."""

import subprocess
import sys

import pytest


@pytest.mark.parametrize("key", ["", "synthetic-private-key-not-base64"])
def test_entrypoint_rejects_invalid_settings_without_printing_input(
    key: str, monkeypatch: pytest.MonkeyPatch
) -> None:
    environment = {
        "TELEMETRY_ENABLED": "false",
        "DATABASE__DSN": "postgresql+asyncpg://app_rw:synthetic-db-secret@localhost/test",
        "SECRETS__KEY": key,
    }
    for name, value in environment.items():
        monkeypatch.setenv(name, value)
    result = subprocess.run(
        [sys.executable, "-c", "import sync.serve"],
        capture_output=True,
        text=True,
        timeout=20,
        check=False,
    )
    output = result.stdout + result.stderr
    assert result.returncode != 0
    assert "sync_configuration_invalid" in output
    assert "synthetic-db-secret" not in output
    assert "synthetic-private-key-not-base64" not in output
    assert "input_value" not in output
    assert "Traceback" not in output
