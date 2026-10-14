"""Expo Push Service adapter. iOS delivery needs APNs credentials in the Expo project."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from typing import Any
from uuid import UUID

import httpx

from shared.observability.logging import get_logger
from shared.ports.notifications import Notification, PushTokens
from shared.ports.uow import UnitOfWorkFactory

EXPO_URL = "https://exp.host/--/api/v2/push/send"
BATCH = 100
TICKET_ERROR_CODES = frozenset(
    {
        "DeviceNotRegistered",
        "MessageTooBig",
        "MessageRateExceeded",
        "InvalidCredentials",
        "MismatchSenderId",
        "InvalidProviderToken",
    }
)
logger = get_logger(__name__)


class ExpoPushNotificationSender:
    def __init__(
        self,
        uow: UnitOfWorkFactory,
        http: httpx.AsyncClient,
        *,
        url: str = EXPO_URL,
        access_token: str | None = None,
        attempts: int = 3,
        backoff_s: float = 0.5,
        sleep: Callable[[float], Awaitable[None]] = asyncio.sleep,
    ) -> None:
        self._uow = uow
        self._http = http
        self._url = url
        self._token = access_token
        self._attempts = attempts
        self._backoff = backoff_s
        self._sleep = sleep

    async def send(self, recipients: Sequence[UUID], notification: Notification) -> None:
        targets: list[tuple[UUID, str]] = []
        for recipient in recipients:
            async with self._uow.for_user(recipient) as uow:
                targets.extend(
                    (recipient, token) for token in await uow.repo(PushTokens).for_user(recipient)
                )
        for start in range(0, len(targets), BATCH):
            chunk = targets[start : start + BATCH]
            tickets = await self._post(
                [
                    {
                        "to": token,
                        "title": notification.title,
                        "body": notification.body,
                        "data": dict(notification.data),
                        "sound": "default",
                    }
                    for _, token in chunk
                ]
            )
            for (recipient, token), ticket in zip(chunk, tickets, strict=False):
                details = ticket.get("details") if isinstance(ticket, dict) else None
                error = details.get("error") if isinstance(details, dict) else None
                if isinstance(ticket, dict) and ticket.get("status") == "error":
                    code = (
                        error
                        if isinstance(error, str) and error in TICKET_ERROR_CODES
                        else "unknown"
                    )
                    logger.warning("expo_push_ticket_error", code=code)
                if error == "DeviceNotRegistered":
                    async with self._uow.for_user(recipient) as uow:
                        await uow.repo(PushTokens).delete(recipient, token)

    async def _post(self, messages: list[dict[str, Any]]) -> list[Any]:
        headers = {"accept": "application/json", "content-type": "application/json"}
        if self._token:
            headers["authorization"] = f"Bearer {self._token}"
        for attempt in range(1, self._attempts + 1):
            try:
                response = await self._http.post(
                    self._url, json=messages, headers=headers, timeout=10.0
                )
                if 400 <= response.status_code < 500 and response.status_code != 429:
                    logger.warning("expo_push_http_error", status=response.status_code)
                    return []
                if 200 <= response.status_code < 300:
                    body = response.json()
                    data = body.get("data") if isinstance(body, dict) else None
                    if isinstance(data, list):
                        return data
                    logger.warning("expo_push_response_error", code="invalid_response")
                    return []
                logger.warning(
                    "expo_push_retryable_http_error", status=response.status_code, attempt=attempt
                )
            except (httpx.HTTPError, ValueError) as exc:
                logger.warning("expo_push_error", attempt=attempt, error_type=type(exc).__name__)
            if attempt < self._attempts:
                await self._sleep(self._backoff * 2 ** (attempt - 1))
        logger.warning("expo_push_gave_up", messages=len(messages))
        return []
