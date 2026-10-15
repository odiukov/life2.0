"""users.preferences.body_profile: height, age, sex, activity level, goal override, weight."""

from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol
from uuid import UUID


class BodyProfileRepository(Protocol):
    async def get(self, user_id: UUID) -> dict[str, object]: ...

    async def update(self, user_id: UUID, changes: Mapping[str, object]) -> dict[str, object]:
        """Merge changes; a None value removes that key. Returns the new mapping."""
        ...
