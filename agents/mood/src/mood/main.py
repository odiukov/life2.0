"""FastAPI + A2A application. Production starts it through mood.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from mood.composition import MoodRuntime, build_runtime
from mood.settings import MoodSettings


def create_app(runtime: MoodRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(MoodSettings())
    return create_agent_app(
        title="Mood Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
