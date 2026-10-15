from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any, Protocol


class CalendarAuthError(Exception):
    """Google rejected the access token (401/403)."""


class EventGone(Exception):
    """404/410: the event no longer exists."""


class PreconditionFailed(Exception):
    """412: the event changed since its etag was read."""


class CalendarUnavailable(Exception):
    """Network error, timeout or a 5xx from Google."""


class CalendarRejected(Exception):
    """Any other 4xx; carries only the status code."""

    def __init__(self, status: int) -> None:
        super().__init__(str(status))
        self.status = status


class InvalidGrant(Exception):
    """The refresh token was revoked or expired: the user must reconnect."""


@dataclass(frozen=True, slots=True)
class Tokens:
    access_token: str
    refresh_token: str | None
    expires_in: int


class GoogleOAuth(Protocol):
    async def exchange_code(self, code: str, code_verifier: str) -> Tokens: ...
    async def refresh(self, refresh_token: str) -> Tokens:
        """Raises InvalidGrant or CalendarUnavailable."""
        ...

    async def revoke(self, token: str) -> None:
        """Best effort; never raises."""
        ...


class GoogleCalendar(Protocol):
    async def list_events(
        self, token: str, *, time_min: str, time_max: str, max_results: int, timeout_s: float
    ) -> list[Mapping[str, Any]]: ...
    async def get_event(self, token: str, event_id: str) -> Mapping[str, Any]: ...
    async def create_event(self, token: str, body: Mapping[str, object]) -> Mapping[str, Any]: ...
    async def patch_event(
        self, token: str, event_id: str, patch: Mapping[str, object], etag: str
    ) -> Mapping[str, Any]: ...
    async def delete_event(self, token: str, event_id: str, etag: str) -> None: ...
