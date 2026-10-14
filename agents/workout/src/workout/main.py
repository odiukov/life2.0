"""FastAPI + A2A application. Production starts it through workout.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from workout.composition import WorkoutRuntime, build_runtime
from workout.settings import WorkoutSettings


def create_app(runtime: WorkoutRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(WorkoutSettings())
    return create_agent_app(
        title="Workout Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
