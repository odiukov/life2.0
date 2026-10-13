"""Best-effort extraction of a JSON object from model text output."""

from __future__ import annotations

import json
import re

_FENCE = re.compile(r"```(?:json)?\s*(.*?)```", re.DOTALL)


def extract_json(text: str) -> object:
    candidates = [match.group(1) for match in _FENCE.finditer(text)]
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end > start:
        candidates.append(text[start : end + 1])
    candidates.append(text)
    for candidate in candidates:
        try:
            return json.loads(candidate.strip())
        except json.JSONDecodeError:
            continue
    raise ValueError("no JSON object found in model output")
