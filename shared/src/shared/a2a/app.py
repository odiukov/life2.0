"""FastAPI app for an A2A agent: /health plus the A2A routes; disposes the engine on shutdown."""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Protocol

from a2a.server.agent_execution import AgentExecutor
from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from a2a.server.tasks import TaskStore
from a2a.types import AgentCard
from fastapi import FastAPI


class _Disposable(Protocol):
    async def dispose(self) -> None: ...


def create_agent_app(
    *,
    title: str,
    executor: AgentExecutor,
    task_store: TaskStore,
    card: AgentCard,
    engine: _Disposable,
) -> FastAPI:
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        try:
            yield
        finally:
            await engine.dispose()

    app = FastAPI(title=title, lifespan=lifespan)

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    handler = DefaultRequestHandler(agent_executor=executor, task_store=task_store)
    app.mount("/", A2AStarletteApplication(agent_card=card, http_handler=handler).build())
    return app
