from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol


class TaskRecords(Protocol):
    """Audit row per completed A2A skill run (the `tasks` table)."""

    async def record(
        self,
        *,
        agent: str,
        task_id: str,
        context_id: str | None,
        skill_id: str,
        input_: Mapping[str, object],
        output: str,
        state: str,
    ) -> None: ...
