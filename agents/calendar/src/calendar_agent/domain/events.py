"""Google Calendar events in the user's zone; the "shape of the day" the dashboard shows."""

from __future__ import annotations

import re
from collections.abc import Mapping, Sequence
from contextlib import suppress
from dataclasses import dataclass
from datetime import date, datetime, time
from zoneinfo import ZoneInfo

FREE_FROM = time(9, 0)
FREE_UNTIL = time(22, 0)
MIN_GAP_MIN = 30
_STOPWORDS = {
    "delete",
    "remove",
    "event",
    "calendar",
    "please",
    "the",
    "a",
    "an",
}


@dataclass(frozen=True, slots=True)
class Event:
    id: str | None
    summary: str
    all_day: bool
    start: datetime | None  # aware, UTC
    end: datetime | None
    day: date | None  # all-day events only
    etag: str | None
    end_day: date | None = None  # Exclusive end for multi-day all-day events.


def _parse(value: object, zone: ZoneInfo) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return (parsed if parsed.tzinfo else parsed.replace(tzinfo=zone)).astimezone(ZoneInfo("UTC"))


def normalize(resource: Mapping[str, object], zone: ZoneInfo) -> Event | None:
    summary = str(resource.get("summary") or resource.get("title") or "")
    start_raw, end_raw = resource.get("start"), resource.get("end")
    event_id = resource.get("id")
    etag = resource.get("etag")
    ident = str(event_id) if event_id else None
    tag = str(etag) if etag else None
    if isinstance(start_raw, Mapping) and "date" in start_raw and "dateTime" not in start_raw:
        try:
            day = date.fromisoformat(str(start_raw["date"]))
        except ValueError:
            return None
        end_day = None
        if isinstance(end_raw, Mapping) and "date" in end_raw:
            with suppress(ValueError):
                end_day = date.fromisoformat(str(end_raw["date"]))
        return Event(ident, summary, True, None, None, day, tag, end_day)
    start_value = start_raw.get("dateTime") if isinstance(start_raw, Mapping) else start_raw
    end_value = end_raw.get("dateTime") if isinstance(end_raw, Mapping) else end_raw
    start, end = _parse(start_value, zone), _parse(end_value, zone)
    if start is None or end is None:
        return None
    return Event(ident, summary, False, start, end, None, tag)


def _bucket(start_local: datetime) -> str:
    return (
        "morning" if start_local.hour < 12 else "afternoon" if start_local.hour < 18 else "evening"
    )


def day_shape(
    events: Sequence[Event], target: date, now: datetime, zone: ZoneInfo
) -> dict[str, object] | None:
    counts = {"morning": 0, "afternoon": 0, "evening": 0}
    all_day: list[str] = []
    intervals: list[tuple[datetime, datetime]] = []
    for e in events:
        if e.all_day:
            all_day.append(e.summary or "All-day event")
            continue
        assert e.start is not None
        assert e.end is not None
        start, end = e.start.astimezone(zone), e.end.astimezone(zone)
        counts[_bucket(start)] += 1
        intervals.append((start, end))
    timed = sum(counts.values())
    if timed == 0 and not all_day:
        return None
    hours: dict[int, int] = {}
    for s, _ in intervals:
        hours[s.hour] = hours.get(s.hour, 0) + 1
    busiest = None
    if hours:
        peak = max(hours.items(), key=lambda kv: (kv[1], -kv[0]))[0]
        busiest = f"{peak:02d}:00-{(peak + 1) % 24:02d}:00"
    free_start: str | None = None
    free_len: int | None = None
    local_now = now.astimezone(zone)
    if intervals and target >= local_now.date():
        cursor = max(local_now, datetime.combine(target, FREE_FROM, tzinfo=zone))
        day_end = datetime.combine(target, FREE_UNTIL, tzinfo=zone)
        for s, interval_end in sorted(intervals):
            if s > cursor:
                gap = int((s - cursor).total_seconds() // 60)
                if gap >= MIN_GAP_MIN:
                    free_start, free_len = cursor.strftime("%H:%M"), gap
                    break
            if interval_end > cursor:
                cursor = interval_end
        if free_start is None and cursor < day_end:
            gap = int((day_end - cursor).total_seconds() // 60)
            if gap >= MIN_GAP_MIN:
                free_start, free_len = cursor.strftime("%H:%M"), gap
    return {
        "events_count": timed,
        "morning_count": counts["morning"],
        "afternoon_count": counts["afternoon"],
        "evening_count": counts["evening"],
        "busiest_hour": busiest,
        "first_free_slot_start": free_start,
        "first_free_slot_len_min": free_len,
        "all_day_events": all_day,
    }


def _words(value: str) -> str:
    return " ".join(re.findall(r"[\w]+", value.lower(), flags=re.UNICODE))


def _tokens(value: str, stopwords: frozenset[str]) -> set[str]:
    return {
        t
        for t in re.findall(r"[\w]+", value.lower(), flags=re.UNICODE)
        if t not in _STOPWORDS and t not in stopwords
    }


def title_matches(query: str, summary: str, stopwords: frozenset[str] = frozenset()) -> bool:
    q, s = _words(query), _words(summary)
    if not q or not s:
        return False
    if q in s or s in q:
        return True
    qt, st = _tokens(query, stopwords), _tokens(summary, stopwords)
    return bool(qt and st and qt & st)


def event_line(e: Event, zone: ZoneInfo) -> str:
    title = e.summary or "Untitled"
    suffix = f" (event_id: {e.id})" if e.id else ""
    if e.all_day or e.start is None or e.end is None:
        return f"• all day: {title}{suffix}"
    start, end = e.start.astimezone(zone), e.end.astimezone(zone)
    return f"• {start:%H:%M}-{end:%H:%M}: {title}{suffix}"


def event_dto(e: Event) -> dict[str, object]:
    return {
        "id": e.id,
        "summary": e.summary,
        "all_day": e.all_day,
        "start": e.start.isoformat() if e.start else None,
        "end": e.end.isoformat() if e.end else None,
        "day": e.day.isoformat() if e.day else None,
        "etag": e.etag,
    }
