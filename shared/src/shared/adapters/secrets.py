"""AES-256-GCM sealing for credentials at rest: version(1) | nonce(12) | ciphertext+tag(16)."""

from __future__ import annotations

import base64
import json
import os
from typing import Any

from cryptography.exceptions import InvalidTag
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from shared.config import SecretsSettings
from shared.ports.secrets import SecretBox, SecretsUnreadable

NONCE = 12


class AesGcmSecretBox:
    def __init__(self, key: bytes, *, version: int = 1) -> None:
        if len(key) != 32:
            raise ValueError("AES-256-GCM needs a 32-byte key")
        self._aead = AESGCM(key)
        self._version = version

    @classmethod
    def from_settings(cls, settings: SecretsSettings) -> AesGcmSecretBox:
        return cls(base64.b64decode(settings.key.get_secret_value()))

    def seal(self, plaintext: bytes) -> bytes:
        nonce = os.urandom(NONCE)
        header = bytes([self._version])
        return header + nonce + self._aead.encrypt(nonce, plaintext, header)

    def open(self, sealed: bytes) -> bytes:
        if len(sealed) < 1 + NONCE + 16 or sealed[0] != self._version:
            raise SecretsUnreadable("unknown format or key version")
        header, nonce, body = sealed[:1], sealed[1 : 1 + NONCE], sealed[1 + NONCE :]
        try:
            return self._aead.decrypt(nonce, body, header)
        except InvalidTag as exc:
            raise SecretsUnreadable("authentication failed") from exc


def seal_json(box: SecretBox, payload: dict[str, Any]) -> bytes:
    return box.seal(json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8"))


def open_json(box: SecretBox, sealed: bytes) -> dict[str, Any]:
    value = json.loads(box.open(sealed).decode("utf-8"))
    if not isinstance(value, dict):
        raise SecretsUnreadable("payload is not an object")
    return value
