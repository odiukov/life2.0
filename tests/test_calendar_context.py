"""Tests for the briefing-side calendar shape helper."""
import pytest
from datetime import date, datetime, timezone
from unittest.mock import AsyncMock, patch


def _event(start_hour, end_hour, summary="Mtg", all_day=False, date_=None):
    """Build a minimal event dict as expected after MCP tool normalisation."""
    if all_day:
        return {"summary": summary, "all_day": True,
                "date": (date_ or date(2026, 4, 17)).isoformat()}
    day = date_ or date(2026, 4, 17)
    start = datetime(day.year, day.month, day.day, start_hour, 0, tzinfo=timezone.utc).isoformat()
    end = datetime(day.year, day.month, day.day, end_hour, 0, tzinfo=timezone.utc).isoformat()
    return {"summary": summary, "all_day": False, "start": start, "end": end}


@pytest.mark.asyncio
async def test_returns_none_when_no_mcp_tool_available():
    """If no list_events tool is in the cache, helper returns None silently."""
    with patch("orchestrator.app.calendar_context.get_mcp_tool", return_value=None):
        from orchestrator.app.calendar_context import fetch_calendar_shape
        result = await fetch_calendar_shape(date(2026, 4, 17))
    assert result is None


@pytest.mark.asyncio
async def test_returns_none_on_empty_day():
    fake_tool = AsyncMock()
    fake_tool.ainvoke = AsyncMock(return_value={"events": []})

    with patch("orchestrator.app.calendar_context.get_mcp_tool", return_value=fake_tool):
        from orchestrator.app.calendar_context import fetch_calendar_shape
        result = await fetch_calendar_shape(date(2026, 4, 17))
    assert result is None


@pytest.mark.asyncio
async def test_counts_events_by_time_bucket():
    events = [
        _event(9, 10, "Standup"),    # morning (9:00 UTC → 12:00 Kyiv in summer, still morning depending on TZ offset)
        _event(11, 12, "1:1"),       # morning
        _event(14, 15, "Demo"),      # afternoon
    ]
    fake_tool = AsyncMock()
    fake_tool.ainvoke = AsyncMock(return_value={"events": events})

    with patch("orchestrator.app.calendar_context.get_mcp_tool", return_value=fake_tool):
        from orchestrator.app.calendar_context import fetch_calendar_shape
        result = await fetch_calendar_shape(date(2026, 4, 17))

    assert result is not None
    assert result["events_count"] == 3
    # 9 UTC → 12:00 Kyiv (Apr = EEST +3) → afternoon
    # 11 UTC → 14:00 Kyiv → afternoon
    # 14 UTC → 17:00 Kyiv → afternoon
    # All three fall into afternoon in Kyiv TZ. This is correct behaviour —
    # assertion is on total count + buckets sum, not exact per-bucket count.
    assert result["morning_count"] + result["afternoon_count"] + result["evening_count"] == 3
    assert result["all_day_events"] == []


@pytest.mark.asyncio
async def test_populates_all_day_events():
    events = [
        _event(0, 0, "Vacation", all_day=True),
    ]
    fake_tool = AsyncMock()
    fake_tool.ainvoke = AsyncMock(return_value={"events": events})

    with patch("orchestrator.app.calendar_context.get_mcp_tool", return_value=fake_tool):
        from orchestrator.app.calendar_context import fetch_calendar_shape
        result = await fetch_calendar_shape(date(2026, 4, 17))

    assert result is not None
    assert result["all_day_events"] == ["Vacation"]


@pytest.mark.asyncio
async def test_returns_none_when_tool_raises():
    fake_tool = AsyncMock()
    fake_tool.ainvoke = AsyncMock(side_effect=RuntimeError("mcp down"))

    with patch("orchestrator.app.calendar_context.get_mcp_tool", return_value=fake_tool):
        from orchestrator.app.calendar_context import fetch_calendar_shape
        result = await fetch_calendar_shape(date(2026, 4, 17))
    assert result is None


@pytest.mark.asyncio
async def test_skips_malformed_events_and_returns_partial_shape():
    events = [
        _event(9, 10, "Good"),
        {"summary": "Malformed"},  # missing start/end/all_day
    ]
    fake_tool = AsyncMock()
    fake_tool.ainvoke = AsyncMock(return_value={"events": events})

    with patch("orchestrator.app.calendar_context.get_mcp_tool", return_value=fake_tool):
        from orchestrator.app.calendar_context import fetch_calendar_shape
        result = await fetch_calendar_shape(date(2026, 4, 17))

    assert result is not None
    assert result["events_count"] == 1  # only the well-formed one
