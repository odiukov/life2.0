"""Mood agent HTTP entrypoint."""
from shared.telemetry import init_telemetry, instrument_fastapi_app

init_telemetry("agent-mood")

import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from fastapi import FastAPI

from shared.a2a_store import PostgresTaskStore

from .executor import MoodAgentExecutor
from .skills import build_agent_card

logger = logging.getLogger(__name__)

app = FastAPI(title="Mood Agent")
instrument_fastapi_app(app)


@app.get("/health")
async def health():
    return {"status": "ok"}


def _build_a2a_app() -> A2AStarletteApplication:
    handler = DefaultRequestHandler(
        agent_executor=MoodAgentExecutor(),
        task_store=PostgresTaskStore(agent="mood"),
    )
    return A2AStarletteApplication(agent_card=build_agent_card(), http_handler=handler)


app.mount("/", _build_a2a_app().build())
