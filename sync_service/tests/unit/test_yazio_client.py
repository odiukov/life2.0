import json
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest
from shared.testing.fakes import FixedClock
from sync.adapters.yazio_client import YazioHttpClient
from sync.application.ports import AuthFailed, Credentials, RateLimited, Unavailable
from sync_fixtures import YAZIO_PRODUCT, YAZIO_RECIPE, YAZIO_SIMPLE_ENTRY

NOW = datetime(2026, 10, 13, 9, 0, tzinfo=UTC)
CREDS = Credentials("person@example.com", "hunter2")
DAYS = [date(2026, 10, 13), date(2026, 10, 12)]
GRANT = {"access_token": "at-new", "refresh_token": "rt-new", "expires_in": 3600}
DIARY = {
    "products": [
        {"product_id": "p-oat", "amount": 80, "daytime": "breakfast"},
        {"product_id": "p-oat", "amount": 40, "daytime": "snack"},
        {"product_id": "p-gone", "amount": 10, "daytime": "snack"},
    ],
    "simple_products": [YAZIO_SIMPLE_ENTRY],
    "recipe_portions": [{"recipe_id": "r-1", "portion_count": 2, "daytime": "dinner"}],
}

Handler = Callable[[httpx.Request], httpx.Response]


def server(
    seen: list[httpx.Request], *, oauth: Handler | None = None, diary: Handler | None = None
) -> httpx.MockTransport:
    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        path = request.url.path.removeprefix("/v18")
        if path == "/oauth/token":
            return oauth(request) if oauth else httpx.Response(200, json=GRANT)
        if path == "/user/consumed-items":
            return diary(request) if diary else httpx.Response(200, json=DIARY)
        if path == "/products/p-oat":
            return httpx.Response(200, json=YAZIO_PRODUCT)
        if path == "/recipes/r-1":
            return httpx.Response(200, json=YAZIO_RECIPE)
        return httpx.Response(404)

    return httpx.MockTransport(handle)


def client(transport: httpx.MockTransport) -> YazioHttpClient:
    return YazioHttpClient("cid", "csecret", transport=transport, clock=FixedClock(NOW))


def grants(seen: list[httpx.Request]) -> list[str]:
    return [
        json.loads(r.content)["grant_type"] for r in seen if r.url.path.endswith("/oauth/token")
    ]


async def test_password_grant_then_enriched_days_with_one_lookup_per_product() -> None:
    seen: list[httpx.Request] = []
    bundle, token = await client(server(seen)).fetch(DAYS, CREDS, None)
    body = json.loads(seen[0].content)
    assert body == {
        "client_id": "cid",
        "client_secret": "csecret",
        "grant_type": "password",
        "username": "person@example.com",
        "password": "hunter2",
    }
    assert token == {
        "access_token": "at-new",
        "refresh_token": "rt-new",
        "expires_at": (NOW + timedelta(seconds=3600)).isoformat(),
    }
    assert [day for day, _ in bundle.days] == DAYS
    day_items = bundle.days[0][1]
    assert sorted((i.slot, i.name) for i in day_items) == [
        ("breakfast", "Oatmeal"),
        ("dinner", "Lasagne"),
        ("lunch", "Борщ (AI)"),
        ("snack", "Oatmeal"),
    ]
    assert (
        sum(1 for r in seen if r.url.path.endswith("/products/p-oat")) == 1
    )  # cached across entries and days
    assert bundle.failures == ("product p-gone",)
    assert all(
        r.headers["Authorization"] == "Bearer at-new"
        for r in seen
        if "consumed-items" in r.url.path
    )
    assert [r.url.params["date"] for r in seen if "consumed-items" in r.url.path] == [
        "2026-10-13",
        "2026-10-12",
    ]


async def test_a_valid_token_is_reused_and_not_returned() -> None:
    seen: list[httpx.Request] = []
    stored = {
        "access_token": "at-old",
        "refresh_token": "rt",
        "expires_at": (NOW + timedelta(hours=1)).isoformat(),
    }
    _, token = await client(server(seen)).fetch(DAYS, CREDS, stored)
    assert grants(seen) == []
    assert token is None


async def test_a_token_expiring_within_five_minutes_is_refreshed() -> None:
    seen: list[httpx.Request] = []
    stored = {
        "access_token": "at-old",
        "refresh_token": "rt-old",
        "expires_at": (NOW + timedelta(minutes=2)).isoformat(),
    }
    _, token = await client(server(seen)).fetch(DAYS, CREDS, stored)
    assert grants(seen) == ["refresh_token"]
    assert json.loads(seen[0].content)["refresh_token"] == "rt-old"
    assert token is not None
    assert token["access_token"] == "at-new"


async def test_a_failed_refresh_falls_back_to_the_password() -> None:
    seen: list[httpx.Request] = []

    def oauth(request: httpx.Request) -> httpx.Response:
        grant = json.loads(request.content)["grant_type"]
        return httpx.Response(400) if grant == "refresh_token" else httpx.Response(200, json=GRANT)

    stored = {"access_token": "at-old", "refresh_token": "rt-old", "expires_at": "garbage"}
    _, token = await client(server(seen, oauth=oauth)).fetch(DAYS, CREDS, stored)
    assert grants(seen) == ["refresh_token", "password"]
    assert token is not None


@pytest.mark.parametrize(
    ("response", "expected"),
    [
        (httpx.Response(401, text="bad password person@example.com"), AuthFailed),
        (httpx.Response(400, json={"error": "invalid_grant"}), AuthFailed),
        (httpx.Response(429), RateLimited),
        (httpx.Response(503), Unavailable),
        (httpx.Response(200, json={"token_type": "bearer"}), Unavailable),  # no access_token
    ],
)
async def test_login_failures_become_codes_without_text(
    response: httpx.Response, expected: type[Exception]
) -> None:
    with pytest.raises(expected) as caught:
        await client(server([], oauth=lambda _: response)).fetch(DAYS, CREDS, None)
    assert str(caught.value) == ""
    assert caught.value.__cause__ is None


async def test_transport_errors_are_unavailable() -> None:
    def broken(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("dns", request=request)

    with pytest.raises(Unavailable):
        await client(httpx.MockTransport(broken)).fetch(DAYS, CREDS, None)


async def test_a_429_on_the_diary_stops_and_keeps_the_token() -> None:
    seen: list[httpx.Request] = []
    bundle, token = await client(server(seen, diary=lambda _: httpx.Response(429))).fetch(
        DAYS, CREDS, None
    )
    assert bundle.failures == ("rate_limited",)
    assert bundle.days == ()
    assert sum(1 for r in seen if "consumed-items" in r.url.path) == 1
    assert token is not None


async def test_a_failed_day_is_named_and_the_others_are_kept() -> None:
    def diary(request: httpx.Request) -> httpx.Response:
        return (
            httpx.Response(500)
            if request.url.params["date"] == "2026-10-12"
            else httpx.Response(200, json=DIARY)
        )

    bundle, _ = await client(server([], diary=diary)).fetch(DAYS, CREDS, None)
    assert [day for day, _ in bundle.days] == [date(2026, 10, 13)]
    assert "diary 2026-10-12" in bundle.failures


async def test_check_uses_only_the_password_grant() -> None:
    seen: list[httpx.Request] = []
    await client(server(seen)).check(CREDS)
    assert grants(seen) == ["password"]
    assert len(seen) == 1
    with pytest.raises(AuthFailed):
        await client(server([], oauth=lambda _: httpx.Response(401))).check(CREDS)


@pytest.mark.parametrize("payload", [None, [], {"products": [None]}, {"simple_products": [42]}])
async def test_malformed_diary_keeps_refreshed_token(payload: object) -> None:
    bundle, token = await client(
        server([], diary=lambda _: httpx.Response(200, json=payload))
    ).fetch(DAYS, CREDS, None)
    assert bundle.days == ()
    assert bundle.failures == ("diary 2026-10-13", "diary 2026-10-12")
    assert token is not None


async def test_rate_limit_on_lookup_stops_and_keeps_refreshed_token() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        if request.url.path.endswith("/oauth/token"):
            return httpx.Response(200, json=GRANT)
        if request.url.path.endswith("/user/consumed-items"):
            return httpx.Response(200, json=DIARY)
        return httpx.Response(429)

    bundle, token = await client(httpx.MockTransport(handle)).fetch(DAYS, CREDS, None)
    assert bundle.failures == ("rate_limited",)
    assert len(seen) == 3
    assert token is not None


@pytest.mark.parametrize("grant", [{"access_token": 42}, {**GRANT, "expires_in": 10**100}])
async def test_malformed_grant_is_sanitized(grant: object) -> None:
    with pytest.raises(Unavailable) as caught:
        await client(server([], oauth=lambda _: httpx.Response(200, json=grant))).check(CREDS)
    assert str(caught.value) == ""
    assert caught.value.__suppress_context__
