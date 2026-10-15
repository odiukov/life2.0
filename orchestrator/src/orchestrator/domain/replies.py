"""A short yes/no to a pending confirmation is resolved without the model."""

from __future__ import annotations

import re
import unicodedata
from typing import Literal

CONFIRM = frozenset(
    {"да", "ок", "окей", "ага", "давай", "конечно", "yes", "ok", "okay", "sure", "yep"}
)
REJECT = frozenset({"нет", "не надо", "отмена", "отмени", "no", "nope", "cancel"})


def classify_reply(text: str) -> Literal["confirm", "reject"] | None:
    normalized = text.casefold().strip()
    # Only trailing punctuation and emoji are decoration; never join interrupted words.
    while normalized and (
        normalized[-1].isspace()
        or unicodedata.category(normalized[-1]).startswith(("P", "S"))
        or normalized[-1] in {"\ufe0f", "\ufe0e", "\u200d"}
    ):
        normalized = normalized[:-1]
    normalized = re.sub(r"\s+", " ", normalized)
    if normalized in CONFIRM:
        return "confirm"
    if normalized in REJECT:
        return "reject"
    return None
