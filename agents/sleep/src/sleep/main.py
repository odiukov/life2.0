"""FastAPI + A2A application. Production starts it through sleep.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from sleep.composition import SleepRuntime, build_runtime
from sleep.settings import SleepSettings


def create_app(runtime: SleepRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(SleepSettings())
    return create_agent_app(
        title="Sleep Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
