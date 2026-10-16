"""The shape every agent's attention.items data must have; agents' unit tests call this."""

from __future__ import annotations

from collections.abc import Mapping

from shared.attention import DETAIL_LIMIT, LEVEL_ORDER, MAX_ITEMS, TEXT_LIMIT


def _line(value: object, limit: int) -> bool:
    return (
        isinstance(value, str) and bool(value.strip()) and len(value) <= limit and "\n" not in value
    )


def assert_attention_contract(data: Mapping[str, object] | None) -> None:
    assert data is not None and set(data) == {"items"}, data
    items = data["items"]
    assert isinstance(items, list) and len(items) <= MAX_ITEMS
    ids: set[str] = set()
    previous: tuple[int, int, str] | None = None
    for item in items:
        assert set(item) - {"detail"} == {"id", "level", "rank", "text", "action"}, item
        assert isinstance(item["id"], str) and ":" in item["id"] and item["id"] not in ids, item
        ids.add(item["id"])
        assert item["level"] in LEVEL_ORDER, item
        assert isinstance(item["rank"], int) and not isinstance(item["rank"], bool), item
        assert _line(item["text"], TEXT_LIMIT), item
        assert "detail" not in item or _line(item["detail"], DETAIL_LIMIT), item
        action = item["action"]
        assert isinstance(action, dict) and action.get("type") in ("agent", "task", "profile")
        assert action["type"] != "task" or _line(action.get("prompt"), DETAIL_LIMIT), item
        key = (LEVEL_ORDER[item["level"]], item["rank"], item["id"])
        assert previous is None or previous <= key, "items must be sorted"
        previous = key
