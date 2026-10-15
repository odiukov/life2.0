from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import httpx
import pytest
import respx
from fastapi import FastAPI
from gateway.integrations import OAuthStateRepository, SourceActivity, build_router
from gateway.settings import GatewaySettings
from integration_fakes import InMemoryOAuthStates, InMemorySourceActivity
from shared.ports.credentials import CredentialStore
from shared.ports.skills import SkillCallError, SkillReply
from shared.testing.fakes import (
    FakeSkillClient,
    FixedClock,
    InMemoryCredentialStore,
    InMemoryUnitOfWorkFactory,
)

USER = uuid4()
SYNC = "http://sync.test"


async def me() -> UUID:
    return USER


def settings() -> GatewaySettings:
    return GatewaySettings.model_validate(
        {
            "database": {"dsn": "postgresql://x@localhost/x"},
            "sync_url": SYNC,
            "google_calendar_oauth_client_id": "cid",
            "oauth_state_secret": "s" * 32,
        }
    )


def build(
    home: FakeSkillClient | None = None,
    calendar: FakeSkillClient | None = None,
    store: InMemoryCredentialStore | None = None,
    activity: InMemorySourceActivity | None = None,
    key: bytes | None = b"s" * 32,
):  # type: ignore[no-untyped-def]
    store = store or InMemoryCredentialStore()
    clients = {
        "home": home
        or FakeSkillClient(lambda *a: SkillReply("", {"status": "connected", "version": 1})),
        "calendar": calendar or FakeSkillClient(lambda *a: SkillReply("", {"status": "connected"})),
    }
    uow = InMemoryUnitOfWorkFactory(
        {
            CredentialStore: store,
            OAuthStateRepository: InMemoryOAuthStates(
                FixedClock(datetime(2026, 10, 14, 9, tzinfo=UTC))
            ),
            SourceActivity: activity or InMemorySourceActivity(),
        }
    )
    api = FastAPI()
    api.include_router(
        build_router(
            settings(),
            uow,
            clients.__getitem__,
            httpx.AsyncClient(),
            me,
            clock=FixedClock(datetime(2026, 10, 14, 9, tzinfo=UTC)),
            state_key=key,
        )
    )
    return api, store, clients


async def call(api, method, path, **kwargs):  # type: ignore[no-untyped-def]
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=api), base_url="http://t"
    ) as client:
        return await client.request(method, path, **kwargs)


@respx.mock
async def test_garmin_connect_validates_then_seals(monkeypatch) -> None:
    api, store, _ = build()
    respx.post(f"{SYNC}/integrations/garmin/test").respond(json={"ok": True})
    ok = await call(
        api, "POST", "/integrations/garmin/connect", json={"email": "a@b.c", "password": "pw"}
    )
    assert ok.json() == {"status": "connected"}
    assert store.rows[(USER, "garmin")] == {
        "email": "a@b.c",
        "password": "pw",
    }
    respx.post(f"{SYNC}/integrations/yazio/test").respond(
        401, json={"detail": "invalid Yazio credentials", "code": "auth_failed"}
    )
    bad = await call(
        api, "POST", "/integrations/yazio/connect", json={"email": "a@b.c", "password": "x"}
    )
    assert bad.status_code == 401
    assert bad.json() == {
        "detail": "invalid Yazio credentials",
        "code": "auth_failed",
    }
    assert (USER, "yazio") not in store.rows


@respx.mock
async def test_sync_service_down_is_a_502_with_a_code() -> None:
    api, _, _ = build()
    respx.post(f"{SYNC}/integrations/garmin/test").mock(side_effect=httpx.ConnectError("down"))
    response = await call(
        api, "POST", "/integrations/garmin/connect", json={"email": "a@b.c", "password": "pw"}
    )
    assert response.status_code == 502
    assert response.json()["code"] == "sync_unavailable"


async def test_home_assistant_goes_to_the_home_agent() -> None:
    home = FakeSkillClient(
        lambda skill, *a: SkillReply(
            "",
            {"connected": True, "connected_by": "Ana", "connected_at": "2026-10-14T18:00:00+00:00"}
            if skill == "home.status"
            else {"status": "connected", "version": 1},
        )
    )
    api, _, _ = build(home=home)
    assert (
        await call(
            api,
            "POST",
            "/integrations/ha/connect",
            json={"base_url": "http://ha.local:8123", "token": "long-lived-token"},
        )
    ).json() == {"status": "connected"}
    assert (await call(api, "GET", "/integrations/ha/status")).json()["connected_by"] == "Ana"
    assert [c[0] for c in home.calls] == ["home.connect", "home.status"]


@pytest.mark.parametrize(
    ("code", "status"),
    [
        ("invalid_token", 401),
        ("home_unavailable", 502),
        ("no_household", 409),
        ("invalid_params", 422),
    ],
)
async def test_home_errors_are_readable(code, status) -> None:
    api, _, _ = build(home=FakeSkillClient(lambda *a: SkillCallError(code)))
    response = await call(
        api,
        "POST",
        "/integrations/ha/connect",
        json={"base_url": "http://ha.local:8123", "token": "long-lived-token"},
    )
    assert response.status_code == status
    assert response.json()["code"] == code
    assert response.json()["detail"]


async def test_google_calendar_state_is_signed_single_use_and_user_bound(monkeypatch) -> None:
    calendar = FakeSkillClient(lambda *a: SkillReply("", {"status": "connected"}))
    api, _, _ = build(calendar=calendar)
    start = (await call(api, "POST", "/integrations/google_calendar/start")).json()
    assert "code_challenge=" in start["auth_url"]
    assert "access_type=offline" in start["auth_url"]
    done = await call(
        api,
        "POST",
        "/integrations/google_calendar/callback",
        json={"code": "c", "state": start["state"]},
    )
    assert done.json() == {"status": "connected"}
    skill, _, params, _ = calendar.calls[0]
    assert skill == "calendar.connect"
    assert params["code"] == "c"
    assert len(params["code_verifier"]) >= 43
    replay = await call(
        api,
        "POST",
        "/integrations/google_calendar/callback",
        json={"code": "c", "state": start["state"]},
    )
    assert replay.status_code == 400
    forged = await call(
        api,
        "POST",
        "/integrations/google_calendar/callback",
        json={
            "code": "c",
            "state": start["state"][:-1] + ("0" if start["state"][-1] != "0" else "1"),
        },
    )
    assert forged.status_code == 400


async def test_preflight_counts_only_callers_recent_healthkit_mirrors() -> None:
    now = datetime(2026, 10, 14, 9, tzinfo=UTC)
    activity = InMemorySourceActivity(
        [
            (USER, "Garmin Connect", now - timedelta(days=1)),
            (USER, "Garmin", now - timedelta(days=2)),
            (USER, "Garmin", now - timedelta(days=9)),
            (uuid4(), "Garmin", now),
        ]
    )
    api, _, _ = build(activity=activity)
    found = (await call(api, "GET", "/integrations/preflight", params={"service": "garmin"})).json()
    assert found == {
        "detected": True,
        "sample_count": 2,
        "last_seen": (now - timedelta(days=1)).isoformat(),
    }
    assert (
        await call(api, "GET", "/integrations/preflight", params={"service": "fitbit"})
    ).status_code == 422


@pytest.mark.parametrize("service", ["garmin", "yazio"])
@respx.mock
async def test_disconnect_only_removes_callers_service(service):
    api, store, _ = build()
    other = uuid4()
    await store.put(USER, service, {"password": "mine"})
    await store.put(other, service, {"password": "theirs"})
    response = await call(api, "POST", f"/integrations/{service}/disconnect")
    assert response.json() == {"status": "disconnected"}
    assert await store.get(USER, service) is None
    assert await store.get(other, service) == {"password": "theirs"}


async def test_home_test_and_disconnect_use_named_skills():
    home = FakeSkillClient(
        lambda skill, *a: SkillReply("", {"status": "ok"} if skill == "home.test" else {})
    )
    api, _, _ = build(home=home)
    assert (await call(api, "POST", "/integrations/ha/test")).json() == {"status": "ok"}
    assert (await call(api, "POST", "/integrations/ha/disconnect")).json() == {
        "status": "disconnected"
    }
    assert [c[0] for c in home.calls] == ["home.test", "home.disconnect"]


async def test_calendar_disconnect_and_missing_state_key():
    api, _, clients = build(key=None)
    response = await call(api, "POST", "/integrations/google_calendar/start")
    assert response.status_code == 503
    assert response.json()["code"] == "oauth_not_configured"
    assert (await call(api, "POST", "/integrations/google_calendar/disconnect")).json() == {
        "status": "disconnected"
    }
    assert clients["calendar"].calls[0][0] == "calendar.disconnect"


async def test_calendar_state_cannot_be_used_by_another_user():
    api, _, clients = build()
    start = (await call(api, "POST", "/integrations/google_calendar/start")).json()

    async def other() -> UUID:
        return uuid4()

    api.dependency_overrides[me] = other
    response = await call(
        api,
        "POST",
        "/integrations/google_calendar/callback",
        json={"code": "c", "state": start["state"]},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_state"
    assert clients["calendar"].calls == []


@pytest.mark.parametrize(
    "reason",
    [
        [],
        "private upstream text",
        {"detail": "private upstream text", "code": "unknown_internal_error"},
    ],
)
@respx.mock
async def test_sync_failure_is_safe_even_with_malformed_error_body(reason):
    api, store, _ = build()
    respx.post(f"{SYNC}/integrations/garmin/test").respond(500, json=reason)
    response = await call(
        api, "POST", "/integrations/garmin/connect", json={"email": "a@b.c", "password": "pw"}
    )
    assert response.status_code == 502
    assert response.json()["code"] == "validation_failed"
    assert "private upstream text" not in response.text
    assert await store.get(USER, "garmin") is None


async def test_validation_errors_do_not_echo_credentials():
    api, _, _ = build()
    private = "s" * 513
    response = await call(
        api, "POST", "/integrations/garmin/connect", json={"email": "a@b.c", "password": private}
    )
    assert response.status_code == 422
    assert response.json() == {
        "detail": "Check the request fields and try again.",
        "code": "invalid_request",
    }
    assert private not in response.text


async def test_calendar_rejects_non_ascii_signature_as_bad_state():
    api, _, clients = build()
    response = await call(
        api,
        "POST",
        "/integrations/google_calendar/callback",
        json={"code": "c", "state": f"{uuid4()}.é"},
    )
    assert response.status_code == 400
    assert response.json()["code"] == "bad_state"
    assert clients["calendar"].calls == []
