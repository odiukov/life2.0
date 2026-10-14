"""FastAPI + A2A application. Production starts it through recovery.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from recovery.composition import RecoveryRuntime, build_runtime
from recovery.settings import RecoverySettings


def create_app(runtime: RecoveryRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(RecoverySettings())
    return create_agent_app(
        title="Recovery Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
