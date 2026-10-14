from __future__ import annotations

from dataclasses import dataclass

from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.uow import UnitOfWorkFactory

from sync.application.ports import SyncDirectory
from sync.application.sync_user import SyncUser

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DueReport:
    users: int
    failed: int


class SyncDue:
    """Run by the scheduler every few minutes: sync everyone whose local sync hour has come."""

    def __init__(
        self, *, uow: UnitOfWorkFactory, sync_user: SyncUser, clock: Clock, hour: int
    ) -> None:
        self._uow = uow
        self._sync_user = sync_user
        self._clock = clock
        self._hour = hour

    async def __call__(self, *, force: bool = False) -> DueReport:
        async with self._uow.system() as tx:
            due = await tx.repo(SyncDirectory).due(self._clock.now(), 0 if force else self._hour)
        failed = 0
        for user in due:
            try:
                await self._sync_user(user.user_id, user.services)
            except Exception:  # one user's bug must not starve everyone after them
                failed += 1
                logger.warning("sync_user_crashed", user_id=str(user.user_id), code="unexpected")
        return DueReport(len(due), failed)
