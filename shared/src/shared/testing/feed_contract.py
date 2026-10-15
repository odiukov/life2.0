"""The shape every agent's feed.events data must have; agents' unit tests call this."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from shared.feed import MAX_ITEMS, TEXT_LIMIT


def assert_feed_contract(data: Mapping[str, object] | None, day: date, zone: ZoneInfo) -> None:
    assert data is not None and set(data) == {"items"}, data
    items = data["items"]
    assert isinstance(items, list) and len(items) <= MAX_ITEMS
    start = datetime.combine(day, time.min, tzinfo=zone)
    end = datetime.combine(day + timedelta(days=1), time.min, tzinfo=zone)
    ids: set[str] = set()
    previous: datetime | None = None
    for item in items:
        assert set(item) == {"id", "at", "kind", "text"}, item
        assert isinstance(item["id"], str) and item["id"] and item["id"] not in ids, item
        ids.add(item["id"])
        at = datetime.fromisoformat(item["at"])
        assert at.utcoffset() is not None and start <= at < end, item
        assert previous is None or at <= previous, "items must be newest first"
        previous = at
        assert item["kind"] in ("event", "insight"), item
        text = item["text"]
        assert (
            isinstance(text, str) and text.strip() and len(text) <= TEXT_LIMIT and "\n" not in text
        ), item
