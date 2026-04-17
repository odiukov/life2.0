"""Briefing-side helper: compact 'shape of the day' from Google Calendar MCP tool.

Reuses the already-discovered MCP tools cached in mcp_tools._MCP_TOOLS.
Never raises; returns None when the tool is absent, the day has no events,
or the MCP server errors out. The briefing code skips rendering when None.
"""
from __future__ import annotations

import logging
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from .mcp_tools import get_mcp_tool

logger = logging.getLogger(__name__)

_KYIV = ZoneInfo("Europe/Kyiv")
# Try tool names in order — different MCP servers use slightly different names.
_LIST_TOOL_CANDIDATES = ("list-events", "list_events", "calendar_list_events")


def _pick_list_tool():
    for name in _LIST_TOOL_CANDIDATES:
        tool = get_mcp_tool(name)
        if tool is not None:
            return tool
    return None


def _parse_iso_local(s: str) -> datetime | None:
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, AttributeError, TypeError):
        return None
    return dt.astimezone(_KYIV) if dt.tzinfo else dt.replace(tzinfo=_KYIV)


def _bucket(event: dict) -> str | None:
    """Return 'morning'/'afternoon'/'evening' or None if malformed/all-day."""
    if event.get("all_day"):
        return None
    start = _parse_iso_local(event.get("start", ""))
    if start is None:
        return None
    h = start.hour
    if h < 12:
        return "morning"
    if h < 18:
        return "afternoon"
    return "evening"


async def fetch_calendar_shape(target_date: date) -> dict | None:
    """Return compact shape dict for the given date, or None if unavailable/empty.

    Shape:
      events_count, morning_count, afternoon_count, evening_count,
      busiest_hour, first_free_slot_start, first_free_slot_len_min,
      all_day_events.
    """
    tool = _pick_list_tool()
    if tool is None:
        return None

    payload = {
        "time_min": datetime.combine(target_date, time.min, tzinfo=_KYIV).isoformat(),
        "time_max": datetime.combine(target_date, time.max, tzinfo=_KYIV).isoformat(),
    }
    try:
        result = await tool.ainvoke(payload)
    except Exception as e:
        logger.warning("calendar list tool invocation failed: %s", e)
        return None

    events = result.get("events") if isinstance(result, dict) else result
    if not isinstance(events, list) or not events:
        return None

    morning = afternoon = evening = 0
    all_day: list[str] = []
    timed_intervals: list[tuple[datetime, datetime]] = []

    for ev in events:
        if not isinstance(ev, dict):
            continue
        if ev.get("all_day"):
            summary = ev.get("summary") or ev.get("title") or "All-day event"
            all_day.append(summary)
            continue
        start = _parse_iso_local(ev.get("start", ""))
        end = _parse_iso_local(ev.get("end", ""))
        if start is None or end is None:
            continue
        b = _bucket(ev)
        if b == "morning":
            morning += 1
        elif b == "afternoon":
            afternoon += 1
        elif b == "evening":
            evening += 1
        timed_intervals.append((start, end))

    timed_count = morning + afternoon + evening
    if timed_count == 0 and not all_day:
        return None

    # Busiest hour: hour block with the most event-starts.
    hour_hist: dict[int, int] = {}
    for s, _e in timed_intervals:
        hour_hist[s.hour] = hour_hist.get(s.hour, 0) + 1
    busiest_hour: str | None = None
    if hour_hist:
        peak = max(hour_hist.items(), key=lambda kv: (kv[1], -kv[0]))[0]
        busiest_hour = f"{peak:02d}:00-{(peak + 1) % 24:02d}:00"

    # First free slot today after now(): walk sorted intervals, find first >=30min gap.
    first_free_slot_start: str | None = None
    first_free_slot_len_min: int | None = None
    if timed_intervals:
        sorted_ivs = sorted(timed_intervals, key=lambda t: t[0])
        now_local = datetime.now(_KYIV)
        # Only compute if target_date is today or in the future.
        if target_date >= now_local.date():
            cursor = max(now_local, datetime.combine(target_date, time(9, 0), tzinfo=_KYIV))
            day_end = datetime.combine(target_date, time(22, 0), tzinfo=_KYIV)
            for s, e in sorted_ivs:
                if s > cursor:
                    gap_min = int((s - cursor).total_seconds() // 60)
                    if gap_min >= 30:
                        first_free_slot_start = cursor.strftime("%H:%M")
                        first_free_slot_len_min = gap_min
                        break
                if e > cursor:
                    cursor = e
            if first_free_slot_start is None and cursor < day_end:
                gap_min = int((day_end - cursor).total_seconds() // 60)
                if gap_min >= 30:
                    first_free_slot_start = cursor.strftime("%H:%M")
                    first_free_slot_len_min = gap_min

    return {
        "events_count": timed_count,
        "morning_count": morning,
        "afternoon_count": afternoon,
        "evening_count": evening,
        "busiest_hour": busiest_hour,
        "first_free_slot_start": first_free_slot_start,
        "first_free_slot_len_min": first_free_slot_len_min,
        "all_day_events": all_day,
    }
