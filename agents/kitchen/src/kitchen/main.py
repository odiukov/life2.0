"""FastAPI + A2A application. Production starts it through kitchen.serve."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from fastapi import FastAPI

from kitchen.composition import KitchenRuntime, build_runtime
from kitchen.settings import KitchenSettings


def create_app(runtime: KitchenRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(KitchenSettings())

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await built.engine.dispose()

    app = FastAPI(
        title="Kitchen Agent", lifespan=lifespan, openapi_url=None, docs_url=None, redoc_url=None
    )

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    handler = DefaultRequestHandler(agent_executor=built.executor, task_store=built.task_store)
    app.mount("/", A2AStarletteApplication(agent_card=built.card, http_handler=handler).build())
    return app
