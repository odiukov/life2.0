"""FastAPI + A2A application. Production starts it through medication.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from medication.composition import MedicationRuntime, build_runtime
from medication.settings import MedicationSettings


def create_app(runtime: MedicationRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(MedicationSettings())
    return create_agent_app(
        title="Medication Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
