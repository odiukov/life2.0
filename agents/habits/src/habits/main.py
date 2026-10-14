"""FastAPI + A2A application. Production starts it through habits.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from habits.composition import HabitsRuntime, build_runtime
from habits.settings import HabitsSettings


def create_app(runtime: HabitsRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(HabitsSettings())
    return create_agent_app(
        title="Habits Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
