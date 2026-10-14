"""Resolving free-text references to inventory and newly added product names."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal
from uuid import UUID

from kitchen.application.ports import TextMatcher
from kitchen.application.schema import AddItem
from kitchen.domain.model import Batch, Status, Unit
from kitchen.domain.rules import normalize_name
from kitchen.domain.units import normalize_quantity

CANDIDATE_MIN_SCORE = 50.0
CONFIDENT_SCORE = 85.0
CONFIDENT_LEAD = 10.0
MAX_CANDIDATES = 5


@dataclass(frozen=True, slots=True)
class Resolved:
    name: str


@dataclass(frozen=True, slots=True)
class Ambiguous:
    ref: str
    candidates: list[str]


@dataclass(frozen=True, slots=True)
class NotFound:
    ref: str


@dataclass(frozen=True, slots=True)
class ReferenceCandidate:
    """Retain each batch's identity and unit for later compatibility clarification."""

    name: str
    unit: Unit
    batch_id: UUID | None


@dataclass(frozen=True, slots=True)
class ResolutionContext:
    candidates: tuple[ReferenceCandidate, ...]

    @property
    def names(self) -> list[str]:
        return sorted({candidate.name for candidate in self.candidates})

    def for_name(self, name: str) -> tuple[ReferenceCandidate, ...]:
        normalized = normalize_name(name)
        return tuple(candidate for candidate in self.candidates if candidate.name == normalized)


def build_resolution_context(
    batches: Sequence[Batch], adds: Sequence[AddItem]
) -> ResolutionContext:
    """Include additions so later operations in the message can refer to them.

    Matching uses names only. Keep every candidate's base unit, including incompatible
    units, so the graph can request clarification instead of silently losing a reference.
    """
    candidates = [
        ReferenceCandidate(normalize_name(batch.name), batch.unit, batch.id)
        for batch in batches
        if batch.status is Status.ACTIVE
    ]
    for item in adds:
        _, unit = normalize_quantity(Decimal(1), item.unit)
        candidates.append(ReferenceCandidate(normalize_name(item.name), unit, None))
    return ResolutionContext(tuple(candidates))


def resolve_ref(
    ref: str, names: Sequence[str], matcher: TextMatcher
) -> Resolved | Ambiguous | NotFound:
    query = normalize_name(ref)
    unique = sorted({normalize_name(name) for name in names})
    if query in unique:
        return Resolved(query)
    ranked = [
        candidate
        for candidate in matcher.rank(query, unique, limit=MAX_CANDIDATES)
        if candidate.score >= CANDIDATE_MIN_SCORE
    ]
    if not ranked:
        return NotFound(ref)
    best = ranked[0]
    if best.score >= CONFIDENT_SCORE and (
        len(ranked) == 1 or best.score - ranked[1].score >= CONFIDENT_LEAD
    ):
        return Resolved(best.key)
    return Ambiguous(ref, [candidate.key for candidate in ranked])
