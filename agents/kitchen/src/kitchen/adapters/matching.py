"""Fuzzy matching of free-text item references."""

from __future__ import annotations

from collections.abc import Sequence

from rapidfuzz import fuzz, process

from kitchen.application.ports import MatchCandidate


class RapidfuzzMatcher:
    def rank(self, query: str, choices: Sequence[str], *, limit: int) -> list[MatchCandidate]:
        if not choices:
            return []
        results = process.extract(query, list(choices), scorer=fuzz.WRatio, limit=limit)
        return [MatchCandidate(key=choice, score=float(score)) for choice, score, _ in results]
