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
    assert {"/household", "/household/invites", "/household/join"} <= paths
    await gateway.aclose()
