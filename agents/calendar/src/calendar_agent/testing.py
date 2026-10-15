from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from calendar_agent.application.ports import (
    CalendarUnavailable,
    EventGone,
    InvalidGrant,
    PreconditionFailed,
    Tokens,
)


class FakeGoogleOAuth:
    def __init__(self) -> None:
        self.refresh_error: Exception | None = None
        self.refreshed = 0
        self.revoked: list[str] = []

    async def exchange_code(self, code: str, code_verifier: str) -> Tokens:
        if code == "bad":
            raise InvalidGrant
        return Tokens("access-1", "refresh-1", 3600)

    async def refresh(self, refresh_token: str) -> Tokens:
        self.refreshed += 1
        if self.refresh_error is not None:
            raise self.refresh_error
        return Tokens(f"access-{self.refreshed + 1}", None, 3600)

    async def revoke(self, token: str) -> None:
        self.revoked.append(token)


class FakeGoogleCalendar:
    """Events keyed by id with integer etags; If-Match is enforced like Google does."""

    def __init__(self, events: list[dict[str, Any]] | None = None) -> None:
        self.events = {str(e["id"]): dict(e) for e in events or []}
        self.unavailable = False
        self.tokens: list[str] = []

    def _check(self, token: str) -> None:
        self.tokens.append(token)
        if self.unavailable:
            raise CalendarUnavailable

    async def list_events(
        self, token: str, *, time_min: str, time_max: str, max_results: int, timeout_s: float
    ) -> list[Mapping[str, Any]]:
        self._check(token)
        selected: list[Mapping[str, Any]] = [
            dict(e)
            for e in self.events.values()
            if time_min[:10]
            <= str((e.get("start") or {}).get("dateTime") or (e.get("start") or {}).get("date"))[
                :10
            ]
            <= time_max[:10]
        ]
        return selected[:max_results]

    async def get_event(self, token: str, event_id: str) -> Mapping[str, Any]:
        self._check(token)
        if event_id not in self.events:
            raise EventGone
        return dict(self.events[event_id])

    async def create_event(self, token: str, body: Mapping[str, object]) -> Mapping[str, Any]:
        self._check(token)
        new = {"id": f"new-{len(self.events) + 1}", "etag": '"1"', **body}
        self.events[str(new["id"])] = new
        return new

    async def patch_event(
        self, token: str, event_id: str, patch: Mapping[str, object], etag: str
    ) -> Mapping[str, Any]:
        self._check(token)
        current = self.events.get(event_id)
        if current is None:
            raise EventGone
        if current.get("etag") != etag:
            raise PreconditionFailed
        current.update(patch)
        current["etag"] = f'"{int(str(etag).strip(chr(34))) + 1}"'
        return dict(current)

    async def delete_event(self, token: str, event_id: str, etag: str) -> None:
        self._check(token)
        current = self.events.get(event_id)
        if current is None:
            raise EventGone
        if current.get("etag") != etag:
            raise PreconditionFailed
        del self.events[event_id]
