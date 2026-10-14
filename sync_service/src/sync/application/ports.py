"""Ports of the sync service."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any, ClassVar, Literal, Protocol
from uuid import UUID

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


@dataclass(frozen=True, slots=True)
class SyncStatus:
    last_attempt_at: datetime | None
    last_success_at: datetime | None
    last_error: str | None


class SyncStateRepository(Protocol):
    async def get(self, user_id: UUID, service: Service) -> SyncStatus | None: ...

    async def claim(
        self, user_id: UUID, service: Service, *, now: datetime, cooldown: timedelta
    ) -> bool:
        """Atomically set last_attempt_at = now unless the last attempt is younger than cooldown."""
        ...

    async def finish(
        self, user_id: UUID, service: Service, *, now: datetime, error: str | None, success: bool
    ) -> None:
        """Record an outcome: last_attempt_at = now, last_error = error; last_success_at = now on success."""
        ...


@dataclass(frozen=True, slots=True)
class DueUser:
    user_id: UUID
    services: tuple[Service, ...]


class SyncDirectory(Protocol):
    """Cross-tenant questions answered by SECURITY DEFINER functions; use through `uow.system()` only."""

    async def due(self, now: datetime, hour: int) -> list[DueUser]: ...

    async def plaintext(self) -> list[tuple[UUID, str]]:
        """(user, service) of credential rows still stored as plaintext."""
        ...
