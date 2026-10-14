"""Notification adapters: PostgreSQL inbox, Expo push, and service composition."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import httpx
from sqlalchemy.ext.asyncio import AsyncConnection

from shared.adapters.notifications.expo import ExpoPushNotificationSender
from shared.adapters.notifications.inbox import SqlNotificationInbox
from shared.adapters.notifications.push_tokens import SqlPushTokens
from shared.adapters.notifications.senders import (
    CompositeNotificationSender,
    InboxNotificationSender,
)
from shared.config import NotificationSettings
from shared.ports.clock import Clock
from shared.ports.notifications import NotificationInbox, NotificationSender, PushTokens
from shared.ports.uow import UnitOfWorkFactory

__all__ = [
    "CompositeNotificationSender",
    "ExpoPushNotificationSender",
    "InboxNotificationSender",
    "SqlNotificationInbox",
    "SqlPushTokens",
    "build_notification_sender",
    "notification_repositories",
]


def notification_repositories() -> dict[type[Any], Callable[[AsyncConnection], Any]]:
    return {NotificationInbox: SqlNotificationInbox, PushTokens: SqlPushTokens}


def build_notification_sender(
    settings: NotificationSettings, *, uow: UnitOfWorkFactory, http: httpx.AsyncClient, clock: Clock
) -> NotificationSender:
    push = None
    if settings.push == "expo":
        token = (
            settings.expo_access_token.get_secret_value() if settings.expo_access_token else None
        )
        push = ExpoPushNotificationSender(uow, http, url=settings.expo_url, access_token=token)
    return CompositeNotificationSender(InboxNotificationSender(uow, clock), push)
