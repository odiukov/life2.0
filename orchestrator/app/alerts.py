from __future__ import annotations

from dataclasses import dataclass

_VALID_SEVERITY = {"info", "warn", "crit"}
_VALID_CATEGORY = {"wellness", "productivity", "lifestyle"}


@dataclass(frozen=True)
class Alert:
    rule_id: str
    severity: str
    message: str
    category: str
    throttle_hours: int = 12

    def __post_init__(self) -> None:
        if self.severity not in _VALID_SEVERITY:
            raise ValueError(f"invalid severity: {self.severity}")
        if self.category not in _VALID_CATEGORY:
            raise ValueError(f"invalid category: {self.category}")
