"""Export gateway routes as a deterministic OpenAPI document without a database connection."""

from __future__ import annotations

import asyncio
import json
import sys
from collections.abc import Sequence
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import APIRouter, FastAPI, Header
from shared.testing.fakes import FakeSkillClient, FakeSpeechToText

from gateway.auth.settings import AuthSettings
from gateway.composition import Gateway, build_gateway
from gateway.settings import GatewaySettings


async def _documented_user(authorization: str | None = Header(default=None)) -> UUID:
    raise NotImplementedError  # OpenAPI uses only this dependency's signature.


def build_documented_gateway() -> Gateway:
    settings = GatewaySettings.model_validate(
        {
            "database": {"dsn": "postgresql://doc:doc@localhost/doc"},
            "secrets": {"key": "AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA="},
        }
    )
    return build_gateway(
        settings,
        auth=AuthSettings(auth_jwt_secret=None),
        skill_client=FakeSkillClient(lambda *args: NotImplementedError()),
        stt=FakeSpeechToText(),
    )


def document_app(gateway: Gateway, extra_routers: Sequence[APIRouter] = ()) -> FastAPI:
    app = FastAPI(title="life-agents gateway", version="1")
    for router in (*gateway.routers, *extra_routers):
        app.include_router(router)
    app.dependency_overrides[gateway.authenticate] = _documented_user
    return app


async def _openapi_document() -> dict[str, Any]:
    gateway = build_documented_gateway()
    try:
        return document_app(gateway).openapi()
    finally:
        await gateway.aclose()


def openapi_document() -> dict[str, Any]:
    return asyncio.run(_openapi_document())


def main() -> None:
    target = Path(sys.argv[1])
    target.write_text(
        json.dumps(openapi_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        "utf-8",
    )


if __name__ == "__main__":
    main()
