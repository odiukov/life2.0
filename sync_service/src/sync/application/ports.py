"""Ports of the sync service. Task 6 appends the sync-state ports to this module."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date
from typing import Any, ClassVar, Literal, Protocol

from sync.domain.garmin import GarminBundle
from sync.domain.yazio import YazioBundle

Service = Literal["garmin", "yazio"]
SERVICES: tuple[Service, ...] = ("garmin", "yazio")
TOKEN_KEYS: Mapping[Service, str] = {"garmin": "garmin_token", "yazio": "yazio_token"}
ErrorCode = Literal["auth_failed", "rate_limited", "unavailable"]


class IntegrationError(Exception):
    """A provider refused or failed. Carries only a code: provider messages may contain emails or tokens."""

    code: ClassVar[ErrorCode]


class AuthFailed(IntegrationError):
    code = "auth_failed"


class RateLimited(IntegrationError):
    code = "rate_limited"


class Unavailable(IntegrationError):
    code = "unavailable"


@dataclass(frozen=True, slots=True)
class Credentials:
    email: str
    password: str = field(repr=False)

    @classmethod
    def from_payload(cls, payload: Mapping[str, Any]) -> Credentials | None:
        email, password = payload.get("email"), payload.get("password")
        if not isinstance(email, str) or not isinstance(password, str) or not email or not password:
            return None
        return cls(email, password)


class GarminClient(Protocol):
    async def fetch(
        self, days: Sequence[date], credentials: Credentials, token: str | None
    ) -> tuple[GarminBundle, str | None]:
        """Raises IntegrationError only when login fails; the returned token (None: keep) must be stored."""
        ...

    async def check(self, credentials: Credentials) -> None:
        """Fresh login; stores nothing. Raises IntegrationError."""
        ...


class YazioClient(Protocol):
    async def fetch(
        self, days: Sequence[date], credentials: Credentials, token: Mapping[str, Any] | None
    ) -> tuple[YazioBundle, dict[str, Any] | None]:
        """Raises IntegrationError only when login fails; the returned token (None: keep) must be stored."""
        ...

    async def check(self, credentials: Credentials) -> None: ...
