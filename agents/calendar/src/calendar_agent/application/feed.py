"""Calendar events of a day as feed items (the calendar agent has no LLM and no health rows)."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from shared.feed import FeedItem

from calendar_agent.domain.events import Event


def feed_items(
    events: Sequence[Event], day: date, zone: ZoneInfo, t: Callable[..., str]
) -> list[FeedItem]:
    start_of_day = datetime.combine(day, time.min, tzinfo=zone)
    end_of_day = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    items = []
    for index, e in enumerate(events):
        title = e.summary.strip() or t("feed.calendar.untitled")
        key = f"calendar:event:{e.id or index}"
        if e.all_day:
            if e.day is None or not (e.day <= day < (e.end_day or e.day + timedelta(days=1))):
                continue
            items.append(
                FeedItem(key, start_of_day, "event", t("feed.calendar.all_day", title=title))
            )
            continue
        if e.start is None or e.end is None or e.start >= end_of_day or e.end <= start_of_day:
            continue
        local = e.start.astimezone(zone)
        at = max(local, start_of_day)  # an event that began yesterday shows at 00:00
        items.append(
            FeedItem(
                key,
                at,
                "event",
                t("feed.calendar.event", time=local.strftime("%H:%M"), title=title),
            )
        )
    return items
