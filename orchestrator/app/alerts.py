"""Alert dataclass.

Either pass a literal `message=` (back-compat for callers that pre-format
their own string), or pass `message_key=` + optional `message_params=`,
which resolve via shared.i18n at construction time. Locale is fixed to
"en" for the literal `message` rendering; mobile reads message_key +
message_params over the wire and resolves locally.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

_VALID_SEVERITY = {"info", "warn", "crit"}
_VALID_CATEGORY = {"wellness", "productivity", "lifestyle"}


@dataclass(frozen=True)
class Alert:
    rule_id: str
    severity: str
    category: str
    message: str = ""
    message_key: str = ""
    message_params: dict[str, Any] = field(default_factory=dict)
    throttle_hours: int = 12
    title: str = ""

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITY:
            raise ValueError(f"invalid severity: {self.severity}")
        if self.category not in _VALID_CATEGORY:
            raise ValueError(f"invalid category: {self.category}")
        if not self.message and not self.message_key:
            raise ValueError("Alert needs message or message_key")
        if not self.message and self.message_key:
            from shared.i18n import t
            object.__setattr__(
                self, "message",
                t(self.message_key, locale="en", **self.message_params),
            )
        if not self.title:
            derived = self.rule_id.split(".")[0].replace("_", " ").title()
            object.__setattr__(self, "title", derived)
