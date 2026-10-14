from datetime import UTC, datetime
from uuid import uuid4

import pytest
from shared.adapters.notifications.senders import (
    CompositeNotificationSender,
    InboxNotificationSender,
)
from shared.ports.notifications import Notification, NotificationInbox
from shared.testing.fakes import (
    FakeNotificationSender,
    FixedClock,
    InMemoryNotificationInbox,
    InMemoryUnitOfWorkFactory,
)

T0 = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
N = Notification("kitchen.digest", "t", "b", {"route": "/kitchen"})


async def test_inbox_sender_writes_one_row_per_recipient_under_their_tenant() -> None:
    inbox = InMemoryNotificationInbox()
    uow = InMemoryUnitOfWorkFactory({NotificationInbox: inbox})
    a, b = uuid4(), uuid4()
    await InboxNotificationSender(uow, FixedClock(T0)).send([a, b], N)
    assert uow.commits == [a, b]
    assert [i.created_at for i in await inbox.page(a, before=None, limit=5)] == [T0]


async def test_composite_ignores_push_failures_but_not_inbox_failures() -> None:
    class Boom:
        async def send(self, recipients, notification):  # type: ignore[no-untyped-def]
            raise RuntimeError("push down")

    inbox = FakeNotificationSender()
    await CompositeNotificationSender(inbox, Boom()).send([uuid4()], N)  # type: ignore[arg-type]
    assert len(inbox.sent) == 1
    with pytest.raises(RuntimeError):
        await CompositeNotificationSender(Boom(), None).send([uuid4()], N)  # type: ignore[arg-type]
