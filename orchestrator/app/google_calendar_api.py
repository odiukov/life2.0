"""Direct Google Calendar v3 REST client.

Replaces the calendar-mcp-lite hop: the orchestrator already holds a per-user
OAuth token in the vault, so an MCP server in front of Google bought nothing —
the LLM never saw its tool schemas, only the local @tool wrappers in
health_agent.py.

Every call resolves a fresh access token via `google_calendar.get_fresh_access_token`,
which returns None when the user has not connected (or the refresh token was
revoked). That case raises `CalendarNotConnected` so callers can tell "reconnect
Google Calendar" apart from "Google returned an error".
"""
from __future__ import annotations

import logging
from typing import Any
from urllib.parse import quote
from uuid import UUID

import httpx

logger = logging.getLogger(__name__)

_BASE = "https://www.googleapis.com/calendar/v3"
DEFAULT_TIMEOUT_SECONDS = 10.0


class CalendarNotConnected(Exception):
    """No usable Google Calendar credentials for this user."""


class CalendarApiError(Exception):
    """Google Calendar returned a non-2xx response."""

    def __init__(self, status_code: int, body: str):
        self.status_code = status_code
        self.body = body
        super().__init__(f"Google Calendar API error {status_code}: {body}")


async def _request(
    user_id: UUID,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: Any | None = None,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> Any:
    from . import google_calendar

    token = await google_calendar.get_fresh_access_token(user_id)
    if not token:
        raise CalendarNotConnected(str(user_id))

    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.request(
            method,
            f"{_BASE}{path}",
            params=params,
            json=json_body,
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
        )
    if response.status_code >= 400:
        raise CalendarApiError(response.status_code, response.text)
    # DELETE returns 204 No Content.
    if response.status_code == 204 or not response.content:
        return None
    return response.json()


def _events_path(calendar_id: str, event_id: str | None = None) -> str:
    path = f"/calendars/{quote(calendar_id, safe='')}/events"
    if event_id is not None:
        path += f"/{quote(event_id, safe='')}"
    return path


async def list_events(
    user_id: UUID,
    *,
    time_min: str,
    time_max: str,
    max_results: int = 20,
    calendar_id: str = "primary",
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
) -> list[dict]:
    """Return raw Google event resources for the window, ordered by start time."""
    data = await _request(
        user_id,
        "GET",
        _events_path(calendar_id),
        params={
            "timeMin": time_min,
            "timeMax": time_max,
            "maxResults": max_results,
            "singleEvents": "true",
            "orderBy": "startTime",
        },
        timeout=timeout,
    )
    items = data.get("items") if isinstance(data, dict) else None
    return items if isinstance(items, list) else []


async def create_event(
    user_id: UUID,
    *,
    summary: str,
    start: str,
    end: str,
    description: str | None = None,
    attendees: list[str] | None = None,
    calendar_id: str = "primary",
) -> dict:
    body: dict[str, Any] = {
        "summary": summary,
        "start": {"dateTime": start},
        "end": {"dateTime": end},
    }
    if description:
        body["description"] = description
    if attendees:
        body["attendees"] = [{"email": email} for email in attendees]
    result = await _request(
        user_id, "POST", _events_path(calendar_id), json_body=body
    )
    return result if isinstance(result, dict) else {}


async def patch_event(
    user_id: UUID,
    *,
    event_id: str,
    patch: dict,
    calendar_id: str = "primary",
) -> dict:
    result = await _request(
        user_id,
        "PATCH",
        _events_path(calendar_id, event_id),
        json_body=patch,
    )
    return result if isinstance(result, dict) else {}


async def delete_event(
    user_id: UUID,
    *,
    event_id: str,
    calendar_id: str = "primary",
) -> None:
    await _request(user_id, "DELETE", _events_path(calendar_id, event_id))
