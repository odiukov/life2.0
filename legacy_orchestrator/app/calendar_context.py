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
        logger.warning("calendar list timed out after %.1fs", _CALENDAR_TIMEOUT_SECONDS)
        return []
    except Exception as e:
        logger.warning("calendar_list_failed error_type=%s", type(e).__name__)
        return []
    return [e for ev in items if (e := _normalize_event(ev))]
