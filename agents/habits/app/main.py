"""Habits agent HTTP entrypoint."""
import logging

from a2a.server.apps import A2AStarletteApplication
from a2a.server.request_handlers import DefaultRequestHandler
from fastapi import FastAPI

from shared.a2a_store import PostgresTaskStore

from .executor import HabitsAgentExecutor
from .skills import build_agent_card

logger = logging.getLogger(__name__)

app = FastAPI(title="Habits Agent")


@app.get("/health")
async def health():
    return {"status": "ok"}


def _build_a2a_app() -> A2AStarletteApplication:
    handler = DefaultRequestHandler(
        agent_executor=HabitsAgentExecutor(),
        task_store=PostgresTaskStore(agent="habits"),
    )
    return A2AStarletteApplication(agent_card=build_agent_card(), http_handler=handler)


app.mount("/", _build_a2a_app().build())
