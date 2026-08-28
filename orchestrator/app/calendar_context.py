"""Compact 'shape of the day' from Google Calendar.

Talks to the Google Calendar REST API directly via google_calendar_api.
Never raises; returns None/[] when the user has not connected the calendar,
the day has no events, or Google errors out.
"""
from __future__ import annotations

import logging
import asyncio
from datetime import date, datetime, time
from uuid import UUID
from zoneinfo import ZoneInfo

from . import google_calendar_api
from .google_calendar_api import CalendarNotConnected

logger = logging.getLogger(__name__)

_KYIV = ZoneInfo("Europe/Kyiv")
# Budget for the whole calendar hop. The briefing path is latency-sensitive:
# a slow calendar must degrade to "no calendar section", never stall the reply.
_CALENDAR_TIMEOUT_SECONDS = 2.0


def _timezone_or_default(timezone_name: str | None = None):
    if timezone_name:
        try:
            return ZoneInfo(timezone_name)
        except Exception:
            pass
    return _KYIV


def _normalize_event(ev: dict) -> dict | None:
    if not isinstance(ev, dict):
        return None
    summary = ev.get("summary") or ev.get("title") or "Untitled"
    start_raw = ev.get("start")
    end_raw = ev.get("end")

    if isinstance(start_raw, dict):
        start_value = start_raw.get("dateTime") or start_raw.get("date")
    else:
        start_value = start_raw
    if isinstance(end_raw, dict):
        end_value = end_raw.get("dateTime") or end_raw.get("date")
    else:
        end_value = end_raw

    all_day = bool(ev.get("all_day")) or (
        isinstance(start_raw, dict) and "date" in start_raw and "dateTime" not in start_raw
    )
    if all_day:
        normalized = {"summary": summary, "all_day": True, "date": start_value}
        if ev.get("id"):
            normalized["id"] = ev["id"]
        return normalized
    if not start_value or not end_value:
        return None
    normalized = {"summary": summary, "all_day": False, "start": start_value, "end": end_value}
    if ev.get("id"):
        normalized["id"] = ev["id"]
    return normalized


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


async def fetch_calendar_events(
    user_id: UUID,
    target_date: date,
    *,
    max_results: int = 20,
    timezone_name: str | None = None,
) -> list[dict]:
    tz = _timezone_or_default(timezone_name)
    try:
        items = await asyncio.wait_for(
            google_calendar_api.list_events(
                user_id,
                time_min=datetime.combine(target_date, time.min, tzinfo=tz).isoformat(),
                time_max=datetime.combine(target_date, time.max, tzinfo=tz).isoformat(),
                max_results=max_results,
                timeout=_CALENDAR_TIMEOUT_SECONDS,
            ),
            timeout=_CALENDAR_TIMEOUT_SECONDS,
        )
    except CalendarNotConnected:
        return []
    except TimeoutError:
        logger.warning(
            "calendar list timed out after %.1fs", _CALENDAR_TIMEOUT_SECONDS
        )
        return []
    except Exception as e:
        logger.warning("calendar list failed: %s", e)
        return []
    return [e for ev in items if (e := _normalize_event(ev))]


async def fetch_calendar_shape(
    target_date: date,
    user_id: UUID | None = None,
    *,
    timezone_name: str | None = None,
) -> dict | None:
    """Return compact shape dict for the given date, or None if unavailable/empty.

    Shape:
      events_count, morning_count, afternoon_count, evening_count,
      busiest_hour, first_free_slot_start, first_free_slot_len_min,
      all_day_events.
    """
    if user_id is None:
        return None
    events = await fetch_calendar_events(
        user_id, target_date, timezone_name=timezone_name
    )

    if not events:
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
