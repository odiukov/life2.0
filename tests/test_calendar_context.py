"""Tests for the calendar shape helper.

Fixtures use raw Google Calendar event resources — that is what
google_calendar_api.list_events returns now that the MCP hop is gone, so
_normalize_event is exercised on the real wire shape.
"""
import asyncio
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch
from uuid import UUID

import pytest

USER = UUID("00000000-0000-0000-0000-000000000001")


def _event(start_hour, end_hour, summary="Mtg", all_day=False, date_=None):
    """Build a minimal Google Calendar event resource."""
    day = date_ or date(2026, 4, 17)
    if all_day:
        return {"summary": summary, "start": {"date": day.isoformat()},
                "end": {"date": day.isoformat()}}
    start = datetime(day.year, day.month, day.day, start_hour, 0, tzinfo=timezone.utc).isoformat()
    end = datetime(day.year, day.month, day.day, end_hour, 0, tzinfo=timezone.utc).isoformat()
    return {"summary": summary, "start": {"dateTime": start}, "end": {"dateTime": end}}


def _with_events(events):
    """Patch the REST client to return the given raw event list."""
    return patch(
        "orchestrator.app.google_calendar_api.list_events",
        new=AsyncMock(return_value=events),
    )


@pytest.mark.asyncio
async def test_returns_none_without_user_id():
    """Calendar is per-user only — no user_id means no calendar."""
    from orchestrator.app.calendar_context import fetch_calendar_shape
    assert await fetch_calendar_shape(date(2026, 4, 17)) is None


@pytest.mark.asyncio
async def test_returns_none_when_calendar_not_connected():
    from orchestrator.app.calendar_context import fetch_calendar_shape
    from orchestrator.app.google_calendar_api import CalendarNotConnected

    with patch(
        "orchestrator.app.google_calendar_api.list_events",
        new=AsyncMock(side_effect=CalendarNotConnected("no creds")),
    ):
        result = await fetch_calendar_shape(date(2026, 4, 17), USER)
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_on_empty_day():
    from orchestrator.app.calendar_context import fetch_calendar_shape

    with _with_events([]):
        result = await fetch_calendar_shape(date(2026, 4, 17), USER)
    assert result is None


@pytest.mark.asyncio
async def test_counts_events_by_time_bucket():
    from orchestrator.app.calendar_context import fetch_calendar_shape

    events = [
        _event(9, 10, "Standup"),
        _event(11, 12, "1:1"),
        _event(14, 15, "Demo"),
    ]
    with _with_events(events):
        result = await fetch_calendar_shape(date(2026, 4, 17), USER)

    assert result is not None
    assert result["events_count"] == 3
    # Buckets are computed in Kyiv local time; assert the total, not the split.
    assert result["morning_count"] + result["afternoon_count"] + result["evening_count"] == 3
    assert result["all_day_events"] == []


@pytest.mark.asyncio
async def test_populates_all_day_events():
    from orchestrator.app.calendar_context import fetch_calendar_shape

    with _with_events([_event(0, 0, "Vacation", all_day=True)]):
        result = await fetch_calendar_shape(date(2026, 4, 17), USER)

    assert result is not None
    assert result["all_day_events"] == ["Vacation"]


@pytest.mark.asyncio
async def test_returns_none_when_api_raises():
    from orchestrator.app.calendar_context import fetch_calendar_shape

    with patch(
        "orchestrator.app.google_calendar_api.list_events",
        new=AsyncMock(side_effect=RuntimeError("google down")),
    ):
        result = await fetch_calendar_shape(date(2026, 4, 17), USER)
    assert result is None


@pytest.mark.asyncio
async def test_per_user_calendar_shape_times_out_instead_of_blocking_dashboard():
    from orchestrator.app import calendar_context

    async def slow_list(*args, **kwargs):
        await asyncio.sleep(1)
        return []

    with patch("orchestrator.app.google_calendar_api.list_events", new=slow_list), \
         patch.object(calendar_context, "_CALENDAR_TIMEOUT_SECONDS", 0.01):
        result = await calendar_context.fetch_calendar_shape(date(2026, 4, 17), USER)

    assert result is None


@pytest.mark.asyncio
async def test_fetch_calendar_events_times_out():
    from orchestrator.app import calendar_context

    async def slow_list(*args, **kwargs):
        await asyncio.sleep(1)
        return []

    with patch("orchestrator.app.google_calendar_api.list_events", new=slow_list), \
         patch.object(calendar_context, "_CALENDAR_TIMEOUT_SECONDS", 0.01):
        events = await calendar_context.fetch_calendar_events(USER, date(2026, 4, 17))

    assert events == []


@pytest.mark.asyncio
async def test_fetch_calendar_events_uses_requested_timezone_for_day_bounds():
    from orchestrator.app import calendar_context

    list_events = AsyncMock(return_value=[])
    with patch("orchestrator.app.google_calendar_api.list_events", new=list_events):
        await calendar_context.fetch_calendar_events(
            USER, date(2026, 5, 5), timezone_name="Europe/Lisbon"
        )

    kwargs = list_events.await_args.kwargs
    assert kwargs["time_min"] == "2026-05-05T00:00:00+01:00"
    assert kwargs["time_max"].startswith("2026-05-05T23:59:59")
    assert kwargs["time_max"].endswith("+01:00")


@pytest.mark.asyncio
async def test_skips_malformed_events_and_returns_partial_shape():
    from orchestrator.app.calendar_context import fetch_calendar_shape

    events = [
        _event(9, 10, "Good"),
        {"summary": "Malformed"},  # no start/end
    ]
    with _with_events(events):
        result = await fetch_calendar_shape(date(2026, 4, 17), USER)

    assert result is not None
    assert result["events_count"] == 1
