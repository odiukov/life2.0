"""Google OAuth and Calendar v3 over httpx. Errors become port exceptions; bodies are never logged."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from urllib.parse import quote

import httpx

from calendar_agent.application.ports import (
    CalendarAuthError,
    CalendarRejected,
    CalendarUnavailable,
    EventGone,
    InvalidGrant,
    PreconditionFailed,
    Tokens,
)

TOKEN_URL = "https://oauth2.googleapis.com/token"
REVOKE_URL = "https://oauth2.googleapis.com/revoke"
API = "https://www.googleapis.com/calendar/v3/calendars/primary/events"


class HttpGoogleOAuth:
    def __init__(
        self,
        http: httpx.AsyncClient,
        *,
        client_id: str,
        client_secret: str | None,
        redirect_uri: str,
    ) -> None:
        self._http = http
        self._client_id = client_id
        self._client_secret = client_secret
        self._redirect_uri = redirect_uri

    async def _token(self, data: dict[str, str]) -> Tokens:
        data["client_id"] = self._client_id
        if self._client_secret:
            data["client_secret"] = self._client_secret
        try:
            response = await self._http.post(TOKEN_URL, data=data, timeout=15.0)
        except httpx.HTTPError:
            raise CalendarUnavailable from None
        if response.status_code in (400, 401):
            try:
                error = response.json().get("error")
            except ValueError:
                error = None
            if error == "invalid_grant":
                raise InvalidGrant
        if response.status_code != 200:
            raise CalendarUnavailable
        body = response.json()
        return Tokens(
            str(body["access_token"]), body.get("refresh_token"), int(body.get("expires_in", 3600))
        )

    async def exchange_code(self, code: str, code_verifier: str) -> Tokens:
        return await self._token(
            {
                "code": code,
                "code_verifier": code_verifier,
                "grant_type": "authorization_code",
                "redirect_uri": self._redirect_uri,
            }
        )

    async def refresh(self, refresh_token: str) -> Tokens:
        return await self._token({"refresh_token": refresh_token, "grant_type": "refresh_token"})

    async def revoke(self, token: str) -> None:
        try:
            await self._http.post(REVOKE_URL, data={"token": token}, timeout=10.0)
        except httpx.HTTPError:
            return


class HttpGoogleCalendar:
    def __init__(self, http: httpx.AsyncClient) -> None:
        self._http = http

    async def _send(
        self, method: str, url: str, token: str, *, timeout_s: float = 10.0, **kwargs: Any
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {token}", **kwargs.pop("headers", {})}
        try:
            response = await self._http.request(
                method, url, headers=headers, timeout=timeout_s, **kwargs
            )
        except httpx.HTTPError:
            raise CalendarUnavailable from None
        code = response.status_code
        if code in (401, 403):
            raise CalendarAuthError
        if code in (404, 410):
            raise EventGone
        if code == 412:
            raise PreconditionFailed
        if code >= 500:
            raise CalendarUnavailable
        if code >= 400:
            raise CalendarRejected(code)
        return response

    def _event_url(self, event_id: str) -> str:
        return f"{API}/{quote(event_id, safe='')}"

    async def list_events(
        self, token: str, *, time_min: str, time_max: str, max_results: int, timeout_s: float
    ) -> list[Mapping[str, Any]]:
        response = await self._send(
            "GET",
            API,
            token,
            timeout_s=timeout_s,
            params={
                "timeMin": time_min,
                "timeMax": time_max,
                "maxResults": max_results,
                "singleEvents": "true",
                "orderBy": "startTime",
            },
        )
        items = response.json().get("items")
        return items if isinstance(items, list) else []

    async def get_event(self, token: str, event_id: str) -> Mapping[str, Any]:
        return dict((await self._send("GET", self._event_url(event_id), token)).json())

    async def create_event(self, token: str, body: Mapping[str, object]) -> Mapping[str, Any]:
        return dict((await self._send("POST", API, token, json=dict(body))).json())

    async def patch_event(
        self, token: str, event_id: str, patch: Mapping[str, object], etag: str
    ) -> Mapping[str, Any]:
        response = await self._send(
            "PATCH", self._event_url(event_id), token, json=dict(patch), headers={"If-Match": etag}
        )
        return dict(response.json())

    async def delete_event(self, token: str, event_id: str, etag: str) -> None:
        await self._send("DELETE", self._event_url(event_id), token, headers={"If-Match": etag})
