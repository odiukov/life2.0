from __future__ import annotations

from typing import Protocol


class SecretsUnreadable(Exception):
    """The sealed value cannot be opened: wrong key, tampering or unknown format."""


class SecretBox(Protocol):
    def seal(self, plaintext: bytes) -> bytes: ...

    def open(self, sealed: bytes) -> bytes:
        """Raises SecretsUnreadable."""
        ...
