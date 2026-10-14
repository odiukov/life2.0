from __future__ import annotations

from collections.abc import Sequence
from uuid import UUID

from shared.observability.logging import get_logger
from shared.ports.clock import Clock
from shared.ports.notifications import Notification, NotificationInbox, NotificationSender
from shared.ports.uow import UnitOfWorkFactory

logger = get_logger(__name__)


class InboxNotificationSender:
    def __init__(self, uow: UnitOfWorkFactory, clock: Clock) -> None:
        self._uow = uow
        self._clock = clock

    async def send(self, recipients: Sequence[UUID], notification: Notification) -> None:
        now = self._clock.now()
        for recipient in recipients:
            async with self._uow.for_user(recipient) as uow:
                await uow.repo(NotificationInbox).add(recipient, notification, created_at=now)


class CompositeNotificationSender:
    """Write the inbox first, then attempt push without blocking inbox delivery."""

    def __init__(self, inbox: NotificationSender, push: NotificationSender | None = None) -> None:
        self._inbox = inbox
        self._push = push

    async def send(self, recipients: Sequence[UUID], notification: Notification) -> None:
        await self._inbox.send(recipients, notification)
        if self._push is None:
            return
        try:
            await self._push.send(recipients, notification)
        except Exception as exc:
            logger.warning("push_failed", kind=notification.kind, error_type=type(exc).__name__)
