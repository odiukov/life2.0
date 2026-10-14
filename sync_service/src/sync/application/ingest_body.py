from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from shared.ports.health_logs import HealthLogRepository
from shared.ports.uow import UnitOfWorkFactory

from sync.application.sync_user import to_health_log
from sync.domain.body import map_body_composition


@dataclass(frozen=True, slots=True)
class IngestResult:
    written: int
    unchanged: int


class IngestBody:
    def __init__(self, *, uow: UnitOfWorkFactory) -> None:
        self._uow = uow

    async def __call__(self, user_id: UUID, entries: Iterable[Mapping[str, Any]]) -> IngestResult:
        rows = map_body_composition(entries)
        if not rows:
            return IngestResult(0, 0)
        async with self._uow.for_user(user_id) as tx:
            logs = tx.repo(HealthLogRepository)
            written = 0
            for row in rows:
                written += await logs.upsert(user_id, to_health_log(row))
        return IngestResult(written, len(rows) - written)
