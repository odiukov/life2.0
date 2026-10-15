"""Synthetic sealing key for gateway composition tests."""

import base64

import pytest


@pytest.fixture(autouse=True)
def sealing_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("SECRETS__KEY", base64.b64encode(b"t" * 32).decode())
