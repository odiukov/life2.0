"""FastAPI application with A2A routes and shared resource cleanup."""

from dataclasses import dataclass

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from home.composition import HomeRuntime, build_runtime
from home.settings import HomeSettings


@dataclass
class _Resources:
    runtime: HomeRuntime

    async def dispose(self) -> None:
        try:
            await self.runtime.engine.dispose()
        finally:
            try:
                await self.runtime.http.aclose()
            finally:
                await self.runtime.pool.aclose()


def create_app(runtime: HomeRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(HomeSettings())
    return create_agent_app(
        title="Home Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=_Resources(built),
    )
