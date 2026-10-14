"""FastAPI + A2A application. Production starts it through nutrition.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from nutrition.composition import NutritionRuntime, build_runtime
from nutrition.settings import NutritionSettings


def create_app(runtime: NutritionRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(NutritionSettings())
    return create_agent_app(
        title="Nutrition Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
