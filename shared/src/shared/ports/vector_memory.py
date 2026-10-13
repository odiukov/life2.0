from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from typing import Protocol
from uuid import UUID


@dataclass(frozen=True, slots=True)
class Memory:
    text: str
    agent: str
    metadata: Mapping[str, str] = field(default_factory=dict)


class VectorMemory(Protocol):
    """Best-effort semantic memory. Implementations swallow backend failures."""

    async def upsert(
        self, *, user_id: UUID, agent: str, key: str, text: str, metadata: Mapping[str, str]
    ) -> None: ...

    async def search(
        self, *, user_id: UUID, query: str, limit: int, agents: Sequence[str] | None = None
    ) -> list[Memory]: ...
