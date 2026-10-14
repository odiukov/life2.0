"""HTTP contract for the authenticated notification inbox and push tokens."""

from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
from fastapi import FastAPI, Header
from gateway.notifications import build_router
from shared.ports.notifications import Notification, NotificationInbox, PushTokens
from shared.testing.fakes import (
    FixedClock,
    InMemoryNotificationInbox,
    InMemoryPushTokens,
    InMemoryUnitOfWorkFactory,
)

T0 = datetime(2026, 10, 14, 18, 0, tzinfo=UTC)


async def dev_user(x_user_id: str = Header(alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


@pytest.fixture
def env() -> tuple[httpx.AsyncClient, InMemoryNotificationInbox, InMemoryPushTokens]:
    inbox, tokens = InMemoryNotificationInbox(), InMemoryPushTokens()
    app = FastAPI()
    app.include_router(
        build_router(
            InMemoryUnitOfWorkFactory({NotificationInbox: inbox, PushTokens: tokens}),
            FixedClock(T0),
            dev_user,
        )
    )
    return (
        httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t"),
        inbox,
        tokens,
    )


async def test_inbox_page_read_and_read_all(
    env: tuple[httpx.AsyncClient, InMemoryNotificationInbox, InMemoryPushTokens],
) -> None:
    http, inbox, _ = env
    user = uuid4()
    headers = {"X-User-Id": str(user)}
    first = await inbox.add(
        user, Notification("kitchen.digest", "t1", "b1", {"route": "/kitchen"}), created_at=T0
    )
    await inbox.add(
        user, Notification("kitchen.digest", "t2", "b2"), created_at=T0 + timedelta(minutes=1)
    )
    response = await http.get("/notifications", params={"limit": 1}, headers=headers)
    assert response.status_code == 200
    page = response.json()
    assert page["unread_count"] == 2
    assert [item["title"] for item in page["items"]] == ["t2"]
    older = (
        await http.get(
            "/notifications", params={"before": page["items"][0]["created_at"]}, headers=headers
        )
    ).json()
    assert [item["title"] for item in older["items"]] == ["t1"]
    assert older["items"][0]["data"] == {"route": "/kitchen"}
    assert (await http.post(f"/notifications/{first}/read", headers=headers)).status_code == 204
    missing = await http.post(f"/notifications/{uuid4()}/read", headers=headers)
    assert (missing.status_code, missing.json()) == (404, {"detail": "notification_not_found"})
    assert (await http.post("/notifications/read-all", headers=headers)).json() == {"updated": 1}
    assert (await http.get("/notifications", headers=headers)).json()["unread_count"] == 0


async def test_tenant_cannot_read_or_mark_another_users_notification(
    env: tuple[httpx.AsyncClient, InMemoryNotificationInbox, InMemoryPushTokens],
) -> None:
    http, inbox, _ = env
    owner, stranger = uuid4(), uuid4()
    item_id = await inbox.add(
        owner, Notification("kitchen.digest", "private", "body"), created_at=T0
    )
    headers = {"X-User-Id": str(stranger)}
    assert (await http.get("/notifications", headers=headers)).json() == {
        "items": [],
        "unread_count": 0,
    }
    response = await http.post(f"/notifications/{item_id}/read", headers=headers)
    assert (response.status_code, response.json()) == (404, {"detail": "notification_not_found"})
    assert (await inbox.unread_count(owner)) == 1


@pytest.mark.parametrize("limit", [0, 101, 500])
async def test_limit_is_bounded(
    env: tuple[httpx.AsyncClient, InMemoryNotificationInbox, InMemoryPushTokens], limit: int
) -> None:
    http, _, _ = env
    response = await http.get(
        "/notifications", params={"limit": limit}, headers={"X-User-Id": str(uuid4())}
    )
    assert response.status_code == 422


@pytest.mark.parametrize("token", ["ExponentPushToken[abc]", "ExpoPushToken[abc]"])
async def test_register_and_delete_push_token(
    env: tuple[httpx.AsyncClient, InMemoryNotificationInbox, InMemoryPushTokens], token: str
) -> None:
    http, _, tokens = env
    user = uuid4()
    headers = {"X-User-Id": str(user)}
    assert (
        await http.post(
            "/me/push-tokens", json={"token": token, "platform": "ios"}, headers=headers
        )
    ).status_code == 204
    assert await tokens.for_user(user) == [token]
    assert (await http.delete(f"/me/push-tokens/{token}", headers=headers)).status_code == 204
    assert await tokens.for_user(user) == []


async def test_token_registration_moves_between_users(
    env: tuple[httpx.AsyncClient, InMemoryNotificationInbox, InMemoryPushTokens],
) -> None:
    http, _, tokens = env
    old_user, new_user = uuid4(), uuid4()
    token = "ExpoPushToken[abc]"
    for user in (old_user, new_user):
        assert (
            await http.post(
                "/me/push-tokens",
                json={"token": token, "platform": "android"},
                headers={"X-User-Id": str(user)},
            )
        ).status_code == 204
    assert await tokens.for_user(old_user) == []
    assert await tokens.for_user(new_user) == [token]
    assert (
        await http.delete(f"/me/push-tokens/{token}", headers={"X-User-Id": str(old_user)})
    ).status_code == 204
    assert await tokens.for_user(new_user) == [token]


@pytest.mark.parametrize(
    ("token", "platform"),
    [("not-a-token", "ios"), ("ExpoPushToken[abc]", "web"), ("ExpoPushToken[]", "ios")],
)
async def test_malformed_push_token_is_rejected(
    env: tuple[httpx.AsyncClient, InMemoryNotificationInbox, InMemoryPushTokens],
    token: str,
    platform: str,
) -> None:
    http, _, tokens = env
    user = uuid4()
    response = await http.post(
        "/me/push-tokens",
        json={"token": token, "platform": platform},
        headers={"X-User-Id": str(user)},
    )
    assert response.status_code == 422
    assert await tokens.for_user(user) == []
