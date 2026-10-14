"""FastAPI + A2A application. Production starts it through body.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from body.composition import BodyRuntime, build_runtime
from body.settings import BodySettings


def create_app(runtime: BodyRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(BodySettings())
    return create_agent_app(
        title="Body Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
