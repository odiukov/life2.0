"""Mood entries in the shape the orchestrator dashboard already reads."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo


class _Row(Protocol):
    @property
    def recorded_at(self) -> datetime: ...

    @property
    def data(self) -> Mapping[str, Any]: ...

    @property
    def source(self) -> str: ...


class _Signal(Protocol):
    @property
    def mood_score(self) -> int | None: ...

    @property
    def energy(self) -> int | None: ...

    @property
    def stress(self) -> int | None: ...

    @property
    def valence(self) -> str | None: ...

    @property
    def tags(self) -> list[str]: ...


def _score(value: object) -> int | None:
    try:
        n = int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return None
    return n if 1 <= n <= 10 else None


@dataclass(frozen=True, slots=True)
class MoodEntry:
    recorded_at: datetime
    mood_score: int | None
    energy: int | None
    stress: int | None
    valence: str | None
    tags: tuple[str, ...]
    raw_text: str
    source_skill: str
    source: str = "manual"

    @classmethod
    def from_row(cls, row: _Row) -> MoodEntry:
        d = row.data
        valence = d.get("valence")
        tags = d.get("tags")
        return cls(
            recorded_at=row.recorded_at,
            mood_score=_score(d.get("mood_score")),
            energy=_score(d.get("energy")),
            stress=_score(d.get("stress")),
            valence=valence if valence in ("pos", "neu", "neg") else None,
            tags=tuple(t for t in tags if isinstance(t, str)) if isinstance(tags, list) else (),
            raw_text=str(d.get("raw_text") or ""),
            source_skill=str(d.get("source_skill") or "log_mood"),
            source=row.source,
        )

    def to_data(self) -> dict[str, object]:
        return {
            "mood_score": self.mood_score,
            "energy": self.energy,
            "stress": self.stress,
            "valence": self.valence,
            "tags": list(self.tags),
            "raw_text": self.raw_text,
            "source_skill": self.source_skill,
        }


def has_signal(e: _Signal) -> bool:
    return any(v is not None for v in (e.mood_score, e.energy, e.stress, e.valence)) or bool(e.tags)


def mood_line(e: MoodEntry, zone: ZoneInfo) -> str:
    local = e.recorded_at.astimezone(zone)
    parts = [
        f"{label}={value}"
        for label, value in (
            ("mood_score", e.mood_score),
            ("energy", e.energy),
            ("stress", e.stress),
            ("valence", e.valence),
        )
        if value is not None
    ]
    if e.tags:
        parts.append(f"tags=[{', '.join(e.tags)}]")
    raw = f' "{e.raw_text[:60]}"' if e.raw_text else ""
    return f"- {local:%Y-%m-%d %H:%M} | " + " | ".join(parts) + raw
