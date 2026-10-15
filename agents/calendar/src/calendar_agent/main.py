"""FastAPI application with A2A routes and shared resource cleanup."""

from dataclasses import dataclass

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from calendar_agent.composition import CalendarRuntime, build_runtime
from calendar_agent.settings import CalendarSettings


@dataclass
class _Resources:
    runtime: CalendarRuntime

    async def dispose(self) -> None:
        try:
            await self.runtime.engine.dispose()
        finally:
            await self.runtime.http.aclose()


def create_app(runtime: CalendarRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(CalendarSettings())
    return create_agent_app(
        title="Calendar Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=_Resources(built),
    )
