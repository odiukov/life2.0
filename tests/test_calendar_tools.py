"""Unit tests for calendar ReAct tools.

Calendar access is per-user, so chat tools must resolve the user from graph
state and call google_calendar_api with that user_id — there is no shared,
boot-time calendar client.
"""
from __future__ import annotations

from datetime import date
from uuid import UUID
from unittest.mock import AsyncMock, patch

import pytest

pytestmark = pytest.mark.asyncio

USER = UUID("00000000-0000-0000-0000-000000000001")


def _state() -> dict:
    return {"messages": [], "toolCalls": [], "userId": str(USER)}


async def test_query_calendar_events_uses_per_user_calendar_context():
    from orchestrator.app.health_agent import query_calendar_events

    events = [
        {
            "summary": "Planning",
            "id": "evt-planning",
            "all_day": False,
            "start": "2026-05-05T10:00:00+03:00",
            "end": "2026-05-05T10:30:00+03:00",
        }
    ]
    with patch(
        "orchestrator.app.calendar_context.fetch_calendar_events",
        new=AsyncMock(return_value=events),
    ) as fetch:
        result = await query_calendar_events.ainvoke({
            "target_date": "2026-05-05",
            "state": _state(),
        })

    fetch.assert_awaited_once_with(USER, date(2026, 5, 5), max_results=20, timezone_name=None)
    assert "Planning" in result
    assert "10:00" in result
    assert "evt-planning" in result


async def test_query_calendar_events_returns_actionable_message_without_user_id():
    from orchestrator.app.health_agent import query_calendar_events

    result = await query_calendar_events.ainvoke({
        "target_date": "2026-05-05",
        "state": {"messages": [], "toolCalls": []},
    })

    assert "Calendar is unavailable" in result


async def test_calendar_prompt_includes_runtime_date_for_relative_queries():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from orchestrator.app.health_agent import _build_system_prompt

    prompt = _build_system_prompt(
        datetime(2026, 5, 5, 9, 30, tzinfo=ZoneInfo("Europe/Kyiv"))
    )

    assert "Current date: 2026-05-05" in prompt
    assert "today/tomorrow/yesterday" in prompt
    assert "query_calendar_events" in prompt


async def test_calendar_prompt_uses_user_timezone_not_kyiv():
    from datetime import datetime
    from zoneinfo import ZoneInfo
    from orchestrator.app.health_agent import _build_system_prompt

    prompt = _build_system_prompt(
        datetime(2026, 5, 5, 23, 30, tzinfo=ZoneInfo("Europe/Lisbon")),
        timezone_name="Europe/Lisbon",
    )

    assert "Current date: 2026-05-05" in prompt
    assert "Europe/Lisbon" in prompt


async def test_query_calendar_events_passes_user_timezone_to_calendar_context():
    from orchestrator.app.health_agent import query_calendar_events

    with patch(
        "orchestrator.app.calendar_context.fetch_calendar_events",
        new=AsyncMock(return_value=[]),
    ) as fetch:
        await query_calendar_events.ainvoke({
            "target_date": "2026-05-05",
            "state": {**_state(), "userTimezone": "Europe/Lisbon"},
        })

    fetch.assert_awaited_once_with(
        USER, date(2026, 5, 5), max_results=20, timezone_name="Europe/Lisbon"
    )


async def test_create_calendar_event_calls_api_with_user_from_state():
    from orchestrator.app.health_agent import create_calendar_event

    create = AsyncMock(return_value={
        "id": "evt-1",
        "summary": "Dentist",
        "htmlLink": "https://calendar.google.com/event?eid=evt-1",
    })
    with patch("orchestrator.app.google_calendar_api.create_event", new=create):
        result = await create_calendar_event.ainvoke({
            "summary": "Dentist",
            "start": "2026-05-05T15:00:00+01:00",
            "end": "2026-05-05T15:30:00+01:00",
            "state": _state(),
        })

    create.assert_awaited_once_with(
        USER,
        summary="Dentist",
        start="2026-05-05T15:00:00+01:00",
        end="2026-05-05T15:30:00+01:00",
    )
    assert "Created calendar event" in result
    assert "evt-1" in result


async def test_create_calendar_event_asks_to_reconnect_when_not_connected():
    from orchestrator.app.health_agent import create_calendar_event
    from orchestrator.app.google_calendar_api import CalendarNotConnected

    with patch(
        "orchestrator.app.google_calendar_api.create_event",
        new=AsyncMock(side_effect=CalendarNotConnected("no creds")),
    ):
        result = await create_calendar_event.ainvoke({
            "summary": "Dentist",
            "start": "2026-05-05T15:00:00+01:00",
            "end": "2026-05-05T15:30:00+01:00",
            "state": _state(),
        })

    assert "Reconnect Google Calendar" in result


async def test_create_calendar_event_reports_google_error_status():
    from orchestrator.app.health_agent import create_calendar_event
    from orchestrator.app.google_calendar_api import CalendarApiError

    with patch(
        "orchestrator.app.google_calendar_api.create_event",
        new=AsyncMock(side_effect=CalendarApiError(400, "bad start time")),
    ):
        result = await create_calendar_event.ainvoke({
            "summary": "Dentist",
            "start": "nonsense",
            "end": "nonsense",
            "state": _state(),
        })

    assert "400" in result


async def test_update_calendar_event_calls_api_with_patch():
    from orchestrator.app.health_agent import update_calendar_event

    patch_event = AsyncMock(return_value={"id": "evt-1", "summary": "Dentist moved"})
    with patch("orchestrator.app.google_calendar_api.patch_event", new=patch_event):
        result = await update_calendar_event.ainvoke({
            "event_id": "evt-1",
            "patch": {"summary": "Dentist moved"},
            "state": _state(),
        })

    patch_event.assert_awaited_once_with(
        USER, event_id="evt-1", patch={"summary": "Dentist moved"}
    )
    assert "Updated calendar event" in result


async def test_delete_calendar_event_calls_api_with_event_id():
    from orchestrator.app.health_agent import delete_calendar_event

    delete = AsyncMock(return_value=None)
    with patch("orchestrator.app.google_calendar_api.delete_event", new=delete):
        result = await delete_calendar_event.ainvoke({
            "event_id": "evt-1",
            "state": _state(),
        })

    delete.assert_awaited_once_with(USER, event_id="evt-1")
    assert "Deleted calendar event" in result


async def test_delete_calendar_event_by_title_resolves_unique_event_id():
    from orchestrator.app.health_agent import delete_calendar_event_by_title

    delete = AsyncMock(return_value=None)
    events = [
        {
            "id": "evt-1",
            "summary": "Dentist",
            "all_day": False,
            "start": "2026-05-05T15:00:00+01:00",
            "end": "2026-05-05T15:30:00+01:00",
        }
    ]
    with patch(
        "orchestrator.app.calendar_context.fetch_calendar_events",
        new=AsyncMock(return_value=events),
    ), patch("orchestrator.app.google_calendar_api.delete_event", new=delete):
        result = await delete_calendar_event_by_title.ainvoke({
            "target_date": "2026-05-05",
            "title_query": "dentist",
            "state": {**_state(), "userTimezone": "Europe/Lisbon"},
        })

    delete.assert_awaited_once_with(USER, event_id="evt-1")
    assert "Deleted calendar event" in result


async def test_delete_calendar_event_by_title_tolerates_extra_words_in_query():
    from orchestrator.app.health_agent import delete_calendar_event_by_title

    delete = AsyncMock(return_value=None)
    events = [
        {
            "id": "evt-1",
            "summary": "Dentist",
            "all_day": False,
            "start": "2026-05-05T15:00:00+01:00",
            "end": "2026-05-05T15:30:00+01:00",
        }
    ]
    with patch(
        "orchestrator.app.calendar_context.fetch_calendar_events",
        new=AsyncMock(return_value=events),
    ), patch("orchestrator.app.google_calendar_api.delete_event", new=delete):
        result = await delete_calendar_event_by_title.ainvoke({
            "target_date": "2026-05-05",
            "title_query": "delete event Dentist please",
            "state": _state(),
        })

    delete.assert_awaited_once_with(USER, event_id="evt-1")
    assert "Deleted calendar event" in result


async def test_delete_calendar_event_by_title_refuses_ambiguous_matches():
    from orchestrator.app.health_agent import delete_calendar_event_by_title

    delete = AsyncMock(return_value=None)
    events = [
        {"id": "evt-1", "summary": "Dentist", "all_day": True, "date": "2026-05-05"},
        {"id": "evt-2", "summary": "Dentist follow-up", "all_day": True, "date": "2026-05-05"},
    ]
    with patch(
        "orchestrator.app.calendar_context.fetch_calendar_events",
        new=AsyncMock(return_value=events),
    ), patch("orchestrator.app.google_calendar_api.delete_event", new=delete):
        result = await delete_calendar_event_by_title.ainvoke({
            "target_date": "2026-05-05",
            "title_query": "dentist",
            "state": _state(),
        })

    delete.assert_not_awaited()
    assert "multiple matching" in result.lower()
