"""FastAPI + A2A application. Production starts it through nutrition.serve."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from fastapi import FastAPI

from nutrition.composition import NutritionRuntime, build_runtime
from nutrition.settings import NutritionSettings


def create_app(runtime: NutritionRuntime | None = None) -> FastAPI:
    if runtime is None:
        settings = NutritionSettings()
        runtime = build_runtime(settings)
    built = runtime

    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await built.engine.dispose()

    app = FastAPI(title="Nutrition Agent", lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    handler = DefaultRequestHandler(agent_executor=built.executor, task_store=built.task_store)
    app.mount("/", A2AStarletteApplication(agent_card=built.card, http_handler=handler).build())
    return app
