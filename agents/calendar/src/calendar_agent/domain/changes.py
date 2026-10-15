from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Literal

Op = Literal["create", "update", "delete"]
_ALLOWED = {"summary", "start", "end", "description", "location"}


class InvalidChange(Exception):
    pass


@dataclass(frozen=True, slots=True)
class ChangeRequest:
    op: Op
    fields: Mapping[str, str]


def _aware(value: str) -> datetime:
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise InvalidChange("bad_time") from None
    if parsed.tzinfo is None:
        raise InvalidChange("time_without_offset")
    return parsed


def parse_change(params: Mapping[str, object]) -> ChangeRequest:
    op = params.get("op")
    raw = params.get("fields") or {}
    if op not in ("create", "update", "delete") or not isinstance(raw, Mapping):
        raise InvalidChange("bad_op")
    fields = {str(k): str(v) for k, v in raw.items() if v is not None}
    if set(fields) - _ALLOWED:
        raise InvalidChange("unknown_field")
    if op == "create" and not {"summary", "start", "end"} <= set(fields):
        raise InvalidChange("missing_field")
    if op == "update" and not fields:
        raise InvalidChange("nothing_to_change")
    if "start" in fields or "end" in fields:
        if not {"start", "end"} <= set(fields):
            raise InvalidChange("start_and_end_together")
        if _aware(fields["end"]) <= _aware(fields["start"]):
            raise InvalidChange("end_before_start")
    return ChangeRequest(op, fields)


def google_body(fields: Mapping[str, str]) -> dict[str, object]:
    body: dict[str, object] = {}
    for key, value in fields.items():
        body[key] = {"dateTime": value} if key in ("start", "end") else value
    return body
