from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any


@dataclass(frozen=True, slots=True)
class Row:
    """One health_logs row produced by a mapper; recorded_at is UTC."""

    agent: str
    type: str
    source: str
    recorded_at: datetime
    data: Mapping[str, Any]
