"""The committed gateway schema is the exact document served by its routers."""

import json
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi import FastAPI
from gateway.openapi import openapi_document

SCHEMA = Path(__file__).resolve().parents[3] / "packages" / "api-client" / "schema" / "gateway.json"


def test_committed_schema_matches_the_routes() -> None:
    expected = json.dumps(openapi_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n"
    assert SCHEMA.read_text("utf-8") == expected


def test_schema_has_every_gateway_route() -> None:
    paths = set(openapi_document()["paths"])
    assert {
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
