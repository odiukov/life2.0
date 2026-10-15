from __future__ import annotations

import re
from typing import Literal

CATEGORIES = (
    "food",
    "housing",
    "transport",
    "subscriptions",
    "software",
    "entertainment",
    "travel",
    "health",
    "utilities",
    "income",
    "transfer",
    "fee",
    "other",
)
Category = Literal[
    "food",
    "housing",
    "transport",
    "subscriptions",
    "software",
    "entertainment",
    "travel",
    "health",
    "utilities",
    "income",
    "transfer",
    "fee",
    "other",
]
_NUMBERS = re.compile(r"[\d\-_/]+")
_SPACES = re.compile(r"\s+")


def desc_key(description: str) -> str:
    """Two descriptions that differ only by dates or ids share one cache key."""
    s = _SPACES.sub(" ", _NUMBERS.sub(" ", (description or "").lower())).strip()
    return s.replace(" ", "-") or "__empty__"
