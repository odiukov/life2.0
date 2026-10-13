from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Protocol
from uuid import UUID


class PeerClient(Protocol):
    async def fetch_artifacts(
        self, *, user_id: UUID, wanted: Mapping[str, str], for_date: date | None = None
    ) -> dict[str, str]:
        """Ask peers for summaries and return only those that answered with text.

        Implementations make depth-one calls. Failed or unavailable peers are omitted.
        """
        ...
