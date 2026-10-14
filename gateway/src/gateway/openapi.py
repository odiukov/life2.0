"""Export gateway routes as a deterministic OpenAPI document without a database connection."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any
from uuid import UUID

from fastapi import FastAPI, Header
from shared.testing.fakes import FakeSkillClient, FakeSpeechToText

from gateway.composition import build_gateway
from gateway.settings import GatewaySettings


async def _documented_user(authorization: str | None = Header(default=None)) -> UUID:
    raise NotImplementedError  # OpenAPI uses only this dependency's signature.


async def _openapi_document() -> dict[str, Any]:
    settings = GatewaySettings.model_validate(
        {"database": {"dsn": "postgresql://doc:doc@localhost/doc"}}
    )
    gateway = build_gateway(
        settings,
        authenticate=_documented_user,
        skill_client=FakeSkillClient(lambda *args: NotImplementedError()),
        stt=FakeSpeechToText(),
    )
    try:
        app = FastAPI(title="life-agents gateway", version="1")
        for router in gateway.routers:
            app.include_router(router)
        return app.openapi()
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
