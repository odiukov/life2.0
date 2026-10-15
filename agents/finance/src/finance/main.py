"""FastAPI + A2A application. Production starts it through finance.serve."""

from __future__ import annotations

from fastapi import FastAPI
from shared.a2a.app import create_agent_app

from finance.composition import FinanceRuntime, build_runtime
from finance.settings import FinanceSettings


def create_app(runtime: FinanceRuntime | None = None) -> FastAPI:
    built = runtime if runtime is not None else build_runtime(FinanceSettings())
    return create_agent_app(
        title="Finance Agent",
        executor=built.executor,
        task_store=built.task_store,
        card=built.card,
        engine=built.engine,
    )
