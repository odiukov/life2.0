import base64
import os

import pytest
from shared.adapters.secrets import AesGcmSecretBox, open_json, seal_json
from shared.config import SecretsSettings
from shared.ports.secrets import SecretsUnreadable

KEY = bytes(range(32))


def test_round_trip_and_random_nonces() -> None:
    box = AesGcmSecretBox(KEY)
    a, b = box.seal(b"hunter2"), box.seal(b"hunter2")
    assert a != b
    assert box.open(a) == b"hunter2"
    assert box.open(b) == b"hunter2"
    assert a[0] == 1
    assert len(a) == 1 + 12 + len(b"hunter2") + 16


def test_tampering_and_wrong_key_fail_closed() -> None:
    sealed = bytearray(AesGcmSecretBox(KEY).seal(b"secret"))
    sealed[-1] ^= 1
    with pytest.raises(SecretsUnreadable):
        AesGcmSecretBox(KEY).open(bytes(sealed))
    with pytest.raises(SecretsUnreadable):
        AesGcmSecretBox(os.urandom(32)).open(AesGcmSecretBox(KEY).seal(b"secret"))
    with pytest.raises(SecretsUnreadable):
        AesGcmSecretBox(KEY).open(b"\x09" + b"\x00" * 40)  # unknown version


def test_json_helpers_keep_unicode() -> None:
    box = AesGcmSecretBox(KEY)
    payload = {"email": "a@b.c", "password": "пароль", "garmin_token": "t"}
    assert open_json(box, seal_json(box, payload)) == payload


def test_settings_reject_a_bad_key() -> None:
    good = base64.b64encode(KEY).decode()
    assert (
        AesGcmSecretBox.from_settings(SecretsSettings.model_validate({"key": good})).open(
            AesGcmSecretBox(KEY).seal(b"x")
        )
        == b"x"
    )
    for bad in ("not-base64!", base64.b64encode(b"short").decode(), ""):
        with pytest.raises(ValueError, match="SECRETS__KEY"):
            SecretsSettings.model_validate({"key": bad})
