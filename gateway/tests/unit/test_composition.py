from uuid import UUID

import pytest
from fastapi import FastAPI, Header
from gateway.composition import GatewayNotConfigured, build_gateway, build_gateway_from_env, mount
from gateway.settings import GatewaySettings


async def dev_user(x_user_id: str = Header(alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


def test_from_env_without_database_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE__DSN", raising=False)
    with pytest.raises(GatewayNotConfigured):
        build_gateway_from_env(authenticate=dev_user)


async def test_mount_adds_household_routes() -> None:
    settings = GatewaySettings.model_validate(
        {"database": {"dsn": "postgresql://u:p@localhost/db"}}
    )
    gateway = build_gateway(settings, authenticate=dev_user)
    app = FastAPI()
    mount(app, gateway)
    paths = set(app.openapi()["paths"])
    assert {
        "/household",
        "/household/invites",
        "/household/join",
        "/kitchen/inventory",
        "/notifications",
        "/notifications/read-all",
        "/notifications/{notification_id}/read",
        "/me/push-tokens",
        "/me/push-tokens/{token}",
        "/voice/transcribe",
    } <= paths
    await gateway.aclose()


async def test_kitchen_routes_use_injected_client_without_database_queries() -> None:
    import httpx
    from shared.ports.skills import SkillReply
    from shared.testing.fakes import FakeSkillClient

    client = FakeSkillClient(lambda s, u, p, t: SkillReply("", {"items": []}))
    settings = GatewaySettings.model_validate(
        {"database": {"dsn": "postgresql://u:p@localhost:1/db"}}
    )
    gateway = build_gateway(settings, authenticate=dev_user, skill_client=client)
    app = FastAPI()
    mount(app, gateway)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gw"
        ) as http:
            response = await http.get(
                "/kitchen/inventory", headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"}
            )
        assert response.json() == {"items": []}
        assert client.calls[0][0] == "kitchen.inventory"
    finally:
        await gateway.aclose()


async def test_composition_uses_configured_a2a_url_and_timeout_and_closes_http() -> None:
    import httpx

    def unavailable(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://configured-kitchen/"
        assert request.extensions["timeout"]["read"] == 10.0
        raise httpx.ConnectError("unavailable", request=request)

    http = httpx.AsyncClient(transport=httpx.MockTransport(unavailable))
    settings = GatewaySettings.model_validate(
        {
            "database": {"dsn": "postgresql://u:p@localhost:1/db"},
            "kitchen_agent_url": "http://configured-kitchen/",
        }
    )
    gateway = build_gateway(settings, authenticate=dev_user, http=http)
    app = FastAPI()
    mount(app, gateway)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gw"
        ) as gw:
            response = await gw.get(
                "/kitchen/digest", headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"}
            )
        assert (response.status_code, response.json()) == (503, {"detail": "kitchen_unavailable"})
    finally:
        await gateway.aclose()
    assert http.is_closed


async def test_voice_route_uses_configured_stt_http_client_and_limit() -> None:
    import httpx

    def transcribe(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == "http://configured-stt/transcribe"
        assert request.extensions["timeout"]["read"] == 7.0
        return httpx.Response(200, json={"text": "hello", "language": "en", "duration_s": 1.0})

    http = httpx.AsyncClient(transport=httpx.MockTransport(transcribe))
    settings = GatewaySettings.model_validate(
        {
            "database": {"dsn": "postgresql://u:p@localhost:1/db"},
            "stt_url": "http://configured-stt",
            "stt_timeout_s": 7.0,
            "voice_max_bytes": 5,
        }
    )
    gateway = build_gateway(settings, authenticate=dev_user, http=http)
    app = FastAPI()
    mount(app, gateway)
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gw"
        ) as gw:
            accepted = await gw.post(
                "/voice/transcribe",
                files={"audio": ("rec.m4a", b"12345", "audio/m4a")},
                data={"language": "en"},
                headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"},
            )
            rejected = await gw.post(
                "/voice/transcribe",
                files={"audio": ("rec.m4a", b"123456", "audio/m4a")},
                headers={"X-User-Id": "00000000-0000-0000-0000-000000000001"},
            )
        assert (accepted.status_code, accepted.json()) == (200, {"text": "hello"})
        assert (rejected.status_code, rejected.json()) == (413, {"detail": "audio_too_long"})
    finally:
        await gateway.aclose()
    assert http.is_closed
