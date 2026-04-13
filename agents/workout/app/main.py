from fastapi import FastAPI
from pydantic import BaseModel
from .agent_card import AGENT_CARD
from .tasks import handle_task

app = FastAPI(title="Workout Agent")


class TaskRequest(BaseModel):
    task: str
    params: dict = {}


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/tasks")
async def create_task(req: TaskRequest):
    result = await handle_task(req.task, req.params)
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
