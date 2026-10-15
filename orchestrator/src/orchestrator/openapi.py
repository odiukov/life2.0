"""Export the public gateway and task routes without a database or agents."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import Any, cast

from gateway.openapi import build_documented_gateway, document_app

from orchestrator.adapters.http import build_router


async def _document() -> dict[str, Any]:
    gateway = build_documented_gateway()
    try:
        # Route handlers only close over these; documentation never calls them.
        unused = cast(Any, object())
        router = build_router(unused, unused, unused, gateway.authenticate)
        return document_app(gateway, [router]).openapi()
    finally:
        await gateway.aclose()


def openapi_document() -> dict[str, Any]:
    return asyncio.run(_document())


def main() -> None:
    Path(sys.argv[1]).write_text(
        json.dumps(openapi_document(), indent=2, sort_keys=True, ensure_ascii=False) + "\n",
        "utf-8",
    )


if __name__ == "__main__":
    main()
