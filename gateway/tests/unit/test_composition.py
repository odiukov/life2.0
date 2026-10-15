from uuid import UUID

import pytest
from fastapi import FastAPI, Header
from gateway.auth.settings import AuthSettings
from gateway.composition import GatewayNotConfigured, build_gateway, build_gateway_from_env, mount
from gateway.settings import GatewaySettings


async def dev_user(x_user_id: str = Header(alias="X-User-Id")) -> UUID:
    return UUID(x_user_id)


def test_from_env_without_database_is_not_configured(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("DATABASE__DSN", raising=False)
    with pytest.raises(GatewayNotConfigured):
        build_gateway_from_env()


async def test_mount_adds_household_routes() -> None:
    settings = GatewaySettings.model_validate(
        {"database": {"dsn": "postgresql://u:p@localhost/db"}}
    )
    gateway = build_gateway(settings, auth=AuthSettings(auth_mode="dev"))
    app = FastAPI()
    mount(app, gateway)
    app.dependency_overrides[gateway.authenticate] = dev_user
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
    gateway = build_gateway(settings, auth=AuthSettings(auth_mode="dev"), skill_client=client)
    app = FastAPI()
    mount(app, gateway)
    app.dependency_overrides[gateway.authenticate] = dev_user
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
    gateway = build_gateway(settings, auth=AuthSettings(auth_mode="dev"), http=http)
    app = FastAPI()
    mount(app, gateway)
    app.dependency_overrides[gateway.authenticate] = dev_user
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
    gateway = build_gateway(settings, auth=AuthSettings(auth_mode="dev"), http=http)
    app = FastAPI()
    mount(app, gateway)
    app.dependency_overrides[gateway.authenticate] = dev_user
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


@pytest.mark.parametrize("from_env", [False, True])
def test_invalid_auth_settings_never_expose_secret(monkeypatch, from_env, caplog):
    import logging
    import traceback

    credential = "synthetic-private-secret"
    monkeypatch.setenv("DATABASE__DSN", "postgresql://u:p@localhost/db")
    monkeypatch.setenv("AUTH_JWT_SECRET", credential)
    build = build_gateway_from_env if from_env else lambda: build_gateway(GatewaySettings())
    with pytest.raises(RuntimeError, match="auth_configuration_invalid") as error:
        build()
    rendered = "".join(traceback.format_exception(error.value))
    logging.getLogger(__name__).error("startup_failed", exc_info=error.value)
    assert credential not in rendered
    assert credential not in caplog.text
    assert error.value.__suppress_context__ is True


@pytest.mark.parametrize("custom", [False, True])
async def test_body_and_calendar_clients_have_longer_configurable_budgets(custom):
    import httpx

    captured = {}

    def unavailable(request: httpx.Request) -> httpx.Response:
        captured[request.url.host] = request.extensions["timeout"]["read"]
        raise httpx.ConnectError("unavailable", request=request)

    overrides = {"body_skill_timeout_s": 120.0, "calendar_skill_timeout_s": 45.0} if custom else {}
    settings = GatewaySettings.model_validate(
        {
            "database": {"dsn": "postgresql://u:p@localhost:1/db"},
            "skill_timeout_s": 7.0,
            **overrides,
        }
    )
    http = httpx.AsyncClient(transport=httpx.MockTransport(unavailable))
    gateway = build_gateway(settings, auth=AuthSettings(auth_mode="dev"), http=http)
    app = FastAPI()
    mount(app, gateway)
    app.dependency_overrides[gateway.authenticate] = dev_user
    headers = {"X-User-Id": "00000000-0000-0000-0000-000000000001"}
    try:
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://gw"
        ) as client:
            imported = await client.post(
                "/me/profile/import-pdf",
                headers=headers,
                files={"file": ("report.pdf", b"%PDF-1.4 report", "application/pdf")},
            )
            disconnected = await client.post(
                "/integrations/google_calendar/disconnect", headers=headers
            )
            kitchen = await client.get("/kitchen/digest", headers=headers)
        assert imported.status_code == 503
        assert disconnected.status_code == 502
        assert kitchen.status_code == 503
        assert captured == {
            "agent-body": 120.0 if custom else 90.0,
            "agent-calendar": 45.0 if custom else 30.0,
            "agent-kitchen": 7.0,
        }
    finally:
        await gateway.aclose()
