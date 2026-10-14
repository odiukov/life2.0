import json
from datetime import UTC, datetime
from unittest.mock import patch
from uuid import uuid4

import httpx
import pytest
import respx
from shared.adapters.notifications.expo import EXPO_URL, ExpoPushNotificationSender
from shared.ports.notifications import Notification, PushTokens
from shared.testing.fakes import InMemoryPushTokens, InMemoryUnitOfWorkFactory

T0 = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)
N = Notification("kitchen.digest", "Скоро испортятся", "курица (завтра)", {"route": "/kitchen"})


async def sender(
    tokens: InMemoryPushTokens, http: httpx.AsyncClient, **kw: object
) -> ExpoPushNotificationSender:
    async def no_sleep(_: float) -> None:
        return None

    return ExpoPushNotificationSender(
        InMemoryUnitOfWorkFactory({PushTokens: tokens}),
        http,
        url=EXPO_URL,
        sleep=no_sleep,
        **kw,  # type: ignore[arg-type]
    )


@respx.mock
async def test_batches_messages_and_forgets_unregistered_devices() -> None:
    tokens = InMemoryPushTokens()
    a, b = uuid4(), uuid4()
    await tokens.upsert(a, "ExponentPushToken[a]", "ios", at=T0)
    await tokens.upsert(b, "ExponentPushToken[b]", "ios", at=T0)
    route = respx.post(EXPO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {"status": "ok", "id": "1"},
                    {
                        "status": "error",
                        "message": "x",
                        "details": {"error": "DeviceNotRegistered"},
                    },
                ]
            },
        )
    )
    async with httpx.AsyncClient() as http:
        await (await sender(tokens, http, access_token="secret")).send([a, b], N)
    sent = route.calls[0].request
    assert sent.headers["authorization"] == "Bearer secret"
    body = json.loads(sent.content)
    assert [m["to"] for m in body] == ["ExponentPushToken[a]", "ExponentPushToken[b]"]
    assert body[0]["data"] == {"route": "/kitchen"}
    assert body[0]["title"] == "Скоро испортятся"
    assert await tokens.for_user(b) == []
    assert await tokens.for_user(a) == ["ExponentPushToken[a]"]


@respx.mock
async def test_retries_transient_errors_then_gives_up_quietly() -> None:
    tokens = InMemoryPushTokens()
    user = uuid4()
    await tokens.upsert(user, "ExponentPushToken[x]", "ios", at=T0)
    route = respx.post(EXPO_URL).mock(
        side_effect=[httpx.Response(503), httpx.ConnectError("x"), httpx.Response(500)]
    )
    async with httpx.AsyncClient() as http:
        await (await sender(tokens, http)).send([user], N)  # must not raise
    assert route.call_count == 3


@respx.mock
async def test_no_tokens_means_no_request() -> None:
    route = respx.post(EXPO_URL)
    async with httpx.AsyncClient() as http:
        await (await sender(InMemoryPushTokens(), http)).send([uuid4()], N)
    assert route.call_count == 0


@respx.mock
async def test_more_than_100_messages_are_split() -> None:
    tokens = InMemoryPushTokens()
    users = [uuid4() for _ in range(150)]
    for i, user in enumerate(users):
        await tokens.upsert(user, f"ExponentPushToken[{i}]", "ios", at=T0)
    route = respx.post(EXPO_URL).mock(
        side_effect=lambda request: httpx.Response(
            200, json={"data": [{"status": "ok"}] * len(json.loads(request.content))}
        )
    )
    async with httpx.AsyncClient() as http:
        await (await sender(tokens, http)).send(users, N)
    assert [len(json.loads(c.request.content)) for c in route.calls] == [100, 50]


@pytest.mark.parametrize("status", [400, 401, 403])
@respx.mock
async def test_nontransient_http_error_is_logged_once_without_private_data(status: int) -> None:
    tokens = InMemoryPushTokens()
    user = uuid4()
    token = "ExponentPushToken[private-device]"
    await tokens.upsert(user, token, "ios", at=T0)
    route = respx.post(EXPO_URL).mock(
        return_value=httpx.Response(status, json={"errors": [{"message": "private response"}]})
    )
    with patch("shared.adapters.notifications.expo.logger.warning") as warning:
        async with httpx.AsyncClient() as http:
            await (await sender(tokens, http)).send([user], N)
    assert route.call_count == 1
    assert warning.call_count == 1
    assert warning.call_args.args == ("expo_push_http_error",)
    assert warning.call_args.kwargs == {"status": status}
    assert token not in str(warning.call_args)
    assert N.body not in str(warning.call_args)
    assert "private response" not in str(warning.call_args)


@respx.mock
async def test_error_ticket_logs_safe_code_and_keeps_registered_device() -> None:
    tokens = InMemoryPushTokens()
    user = uuid4()
    token = "ExponentPushToken[private-device]"
    await tokens.upsert(user, token, "ios", at=T0)
    respx.post(EXPO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status": "error",
                        "message": "private response",
                        "details": {"error": "MessageTooBig"},
                    }
                ]
            },
        )
    )
    with patch("shared.adapters.notifications.expo.logger.warning") as warning:
        async with httpx.AsyncClient() as http:
            await (await sender(tokens, http)).send([user], N)
    assert await tokens.for_user(user) == [token]
    assert warning.call_args.args == ("expo_push_ticket_error",)
    assert warning.call_args.kwargs == {"code": "MessageTooBig"}
    assert token not in str(warning.call_args)
    assert N.body not in str(warning.call_args)
    assert "private response" not in str(warning.call_args)


@respx.mock
async def test_unsafe_ticket_error_code_is_not_logged() -> None:
    tokens = InMemoryPushTokens()
    user = uuid4()
    await tokens.upsert(user, "ExponentPushToken[x]", "ios", at=T0)
    respx.post(EXPO_URL).mock(
        return_value=httpx.Response(
            200,
            json={
                "data": [
                    {
                        "status": "error",
                        "details": {"error": "token private-data"},
                    }
                ]
            },
        )
    )
    with patch("shared.adapters.notifications.expo.logger.warning") as warning:
        async with httpx.AsyncClient() as http:
            await (await sender(tokens, http)).send([user], N)
    assert warning.call_args.kwargs == {"code": "unknown"}
