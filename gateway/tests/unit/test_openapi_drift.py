"""The public schema includes the gateway routes and their component schemas."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from gateway.openapi import openapi_document

SCHEMA = Path(__file__).resolve().parents[3] / "packages" / "api-client" / "schema" / "gateway.json"


def test_committed_schema_matches_the_routes() -> None:
    expected = openapi_document()
    committed = json.loads(SCHEMA.read_text("utf-8"))
    for path, operations in expected["paths"].items():
        assert committed["paths"][path] == operations
    for name, schema in expected["components"]["schemas"].items():
        assert committed["components"]["schemas"][name] == schema


def test_schema_has_every_gateway_route() -> None:
    paths = set(openapi_document()["paths"])
    assert {
        "/me/feed",
        "/me/profile",
        "/me/profile/import-pdf",
        "/integrations/ha/connect",
        "/integrations/ha/test",
        "/integrations/ha/status",
        "/integrations/ha/disconnect",
        "/integrations/google_calendar/start",
        "/integrations/google_calendar/callback",
        "/integrations/google_calendar/disconnect",
        "/integrations/{service}/connect",
        "/integrations/{service}/disconnect",
        "/integrations/preflight",
        "/sync/trigger",
        "/auth/{provider}/start",
        "/auth/google/callback",
        "/auth/apple/callback",
        "/auth/exchange",
        "/auth/refresh",
        "/auth/sign-out",
        "/household",
        "/household/invites",
        "/household/join",
        "/household/join/preview",
        "/household/leave",
        "/household/members/{user_id}",
        "/kitchen/inventory",
        "/kitchen/digest",
        "/kitchen/items/{item_id}/action",
        "/kitchen/undo/{group_id}",
        "/voice/transcribe",
        "/notifications",
        "/notifications/{notification_id}/read",
        "/notifications/read-all",
        "/me/push-tokens",
        "/me/push-tokens/{token}",
    } <= paths


def test_export_closes_gateway_if_schema_generation_fails() -> None:
    class GatewayStub:
        def __init__(self) -> None:
            self.routers: list[object] = []
            self.closed = False
            self.authenticate = lambda: None

        async def aclose(self) -> None:
            self.closed = True

    gateway = GatewayStub()
    with (
        patch("gateway.openapi.build_gateway", return_value=gateway),
        patch.object(FastAPI, "openapi", side_effect=RuntimeError("schema failed")),
        pytest.raises(RuntimeError, match="schema failed"),
    ):
        openapi_document()
    assert gateway.closed


def test_home_status_schema_has_typed_family_connection_fields():
    document = openapi_document()
    schema = document["paths"]["/integrations/ha/status"]["get"]["responses"]["200"]["content"][
        "application/json"
    ]["schema"]
    properties = document["components"]["schemas"][schema["$ref"].split("/")[-1]]["properties"]
    assert properties["connected"]["type"] == "boolean"
    assert {"connected_by", "connected_at"} <= properties.keys()
