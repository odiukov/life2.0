"""Invite codes: 8 Crockford base32 characters, shown as XXXX-XXXX, stored only as sha256."""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass

from household.domain.errors import InviteInvalid

ALPHABET = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"
LENGTH = 8
_LOOKALIKES = str.maketrans({"O": "0", "I": "1", "L": "1"})


@dataclass(frozen=True, slots=True)
class InviteCode:
    value: str

    @classmethod
    def generate(cls, randbelow: Callable[[int], int] = secrets.randbelow) -> InviteCode:
        return cls("".join(ALPHABET[randbelow(len(ALPHABET))] for _ in range(LENGTH)))

    @classmethod
    def parse(cls, raw: str) -> InviteCode:
        value = "".join(raw.split()).replace("-", "").upper().translate(_LOOKALIKES)
        if len(value) != LENGTH or any(ch not in ALPHABET for ch in value):
            raise InviteInvalid
        return cls(value)

    @property
    def display(self) -> str:
        return f"{self.value[:4]}-{self.value[4:]}"

    def digest(self) -> bytes:
        return hashlib.sha256(self.value.encode("ascii")).digest()
