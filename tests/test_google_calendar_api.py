"""Contract tests for the direct Google Calendar v3 client.

Uses httpx.MockTransport so the request Google would actually receive is
asserted — path, query, body, auth header — without a network call.
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, patch
from uuid import UUID

import httpx
import pytest

pytestmark = pytest.mark.asyncio

USER = UUID("00000000-0000-0000-0000-000000000001")


def _transport(handler):
    """Patch AsyncClient so every request goes to `handler`."""
    real_init = httpx.AsyncClient.__init__

    def fake_init(self, *args, **kwargs):
        kwargs["transport"] = httpx.MockTransport(handler)
        real_init(self, *args, **kwargs)

    return patch.object(httpx.AsyncClient, "__init__", fake_init)


def _with_token(token: str | None = "tok-123"):
    return patch(
        "orchestrator.app.google_calendar.get_fresh_access_token",
        new=AsyncMock(return_value=token),
    )


async def test_list_events_sends_window_and_bearer_token():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["url"] = str(request.url)
        seen["auth"] = request.headers.get("Authorization")
        return httpx.Response(200, json={"items": [{"id": "evt-1"}]})

    from orchestrator.app.google_calendar_api import list_events

    with _with_token(), _transport(handler):
        items = await list_events(
            USER,
            time_min="2026-05-05T00:00:00+01:00",
            time_max="2026-05-05T23:59:59+01:00",
            max_results=5,
        )

    assert items == [{"id": "evt-1"}]
    assert seen["auth"] == "Bearer tok-123"
    assert "/calendars/primary/events" in seen["url"]
    assert "maxResults=5" in seen["url"]
    # singleEvents expands recurring series; without it a weekly standup shows
    # up once as its master row instead of on the day being asked about.
    assert "singleEvents=true" in seen["url"]


async def test_list_events_returns_empty_when_google_omits_items():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={})

    from orchestrator.app.google_calendar_api import list_events

    with _with_token(), _transport(handler):
        assert await list_events(
            USER, time_min="a", time_max="b"
        ) == []


async def test_create_event_wraps_start_and_end_in_datetime_objects():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["body"] = json.loads(request.content)
        return httpx.Response(200, json={"id": "evt-1", "summary": "Dentist"})

    from orchestrator.app.google_calendar_api import create_event

    with _with_token(), _transport(handler):
        result = await create_event(
            USER,
            summary="Dentist",
            start="2026-05-05T15:00:00+01:00",
            end="2026-05-05T15:30:00+01:00",
            attendees=["a@example.com"],
        )

    assert seen["method"] == "POST"
    assert seen["body"]["start"] == {"dateTime": "2026-05-05T15:00:00+01:00"}
    assert seen["body"]["end"] == {"dateTime": "2026-05-05T15:30:00+01:00"}
    assert seen["body"]["attendees"] == [{"email": "a@example.com"}]
    assert result["id"] == "evt-1"


async def test_patch_event_uses_patch_verb_and_event_path():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["method"] = request.method
        seen["path"] = request.url.path
        return httpx.Response(200, json={"id": "evt-1"})

    from orchestrator.app.google_calendar_api import patch_event

    with _with_token(), _transport(handler):
        await patch_event(USER, event_id="evt-1", patch={"summary": "moved"})

    assert seen["method"] == "PATCH"
    assert seen["path"].endswith("/calendars/primary/events/evt-1")


async def test_delete_event_tolerates_204_no_content():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(204)

    from orchestrator.app.google_calendar_api import delete_event

    with _with_token(), _transport(handler):
        assert await delete_event(USER, event_id="evt-1") is None


async def test_event_id_is_url_encoded():
    seen = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen["raw_path"] = request.url.raw_path.decode()
        return httpx.Response(204)

    from orchestrator.app.google_calendar_api import delete_event

    with _with_token(), _transport(handler):
        await delete_event(USER, event_id="evt/with slash")

    assert "evt%2Fwith%20slash" in seen["raw_path"]


async def test_non_2xx_raises_calendar_api_error_with_status():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(400, text="bad start time")

    from orchestrator.app.google_calendar_api import CalendarApiError, create_event

    with _with_token(), _transport(handler):
        with pytest.raises(CalendarApiError) as exc:
            await create_event(USER, summary="x", start="nope", end="nope")

    assert exc.value.status_code == 400
    assert "bad start time" in exc.value.body


async def test_missing_token_raises_calendar_not_connected_before_any_request():
    called = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        called["n"] += 1
        return httpx.Response(200, json={})

    from orchestrator.app.google_calendar_api import CalendarNotConnected, list_events

    with _with_token(None), _transport(handler):
        with pytest.raises(CalendarNotConnected):
            await list_events(USER, time_min="a", time_max="b")

    assert called["n"] == 0
