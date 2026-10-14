"""Find which stored name (habit, medication) a person meant, in any language."""

from __future__ import annotations

import re
from collections.abc import Sequence

from pydantic import BaseModel
from rapidfuzz import fuzz, process

from shared.ports.llm import LLMProvider, LLMTask

_NON_ALNUM = re.compile(r"[^a-z0-9]+")
FUZZY_MIN = 88.0
FUZZY_LEAD = 8.0

PICK_SYSTEM = """You map a person's words to one item from a fixed list of names.
Answer with the single list name they mean, exactly as written in the list, or null when none fits.
The person may use another language, a translation, an abbreviation or extra words (such as taking medication or completing a habit).
List: {names}"""


class _Pick(BaseModel):
    name: str | None


def slug(raw: str) -> str:
    return _NON_ALNUM.sub("-", raw.strip().lower()).strip("-") if raw else ""


async def resolve_name(raw: str, names: Sequence[str], *, llm: LLMProvider) -> str | None:
    if not names or not raw.strip():
        return None
    target = slug(raw)
    if target in names:
        return target
    ranked = process.extract(target, list(names), scorer=fuzz.WRatio, limit=2)
    if (
        ranked
        and ranked[0][1] >= FUZZY_MIN
        and (len(ranked) == 1 or ranked[0][1] - ranked[1][1] >= FUZZY_LEAD)
    ):
        return str(ranked[0][0])
    try:
        pick = await llm.structured(
            task=LLMTask.FAST,
            system=PICK_SYSTEM.format(names=", ".join(names)),
            user=raw,
            schema=_Pick,
        )
    except Exception:
        return None
    return pick.name if pick.name in names else None
