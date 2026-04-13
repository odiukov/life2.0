# agents/sleep/app/main.py
import json
import uuid
from datetime import datetime, timezone

from fastapi import FastAPI
from fastapi.responses import StreamingResponse

from shared.a2a import A2ATaskRequest
from .agent_card import AGENT_CARD
from .tasks import handle_task

app = FastAPI(title="Sleep Agent")


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/tasks")
async def create_task(req: A2ATaskRequest):
    return await handle_task(req.task, req.params)


@app.post("/tasks/stream")
async def stream_task(req: A2ATaskRequest):
    task_id = req.id or str(uuid.uuid4())

    async def generate():
        ts = lambda: datetime.now(timezone.utc).isoformat()
        yield _sse({"id": task_id, "status": {"state": "submitted", "timestamp": ts()}})
        yield _sse({"id": task_id, "status": {"state": "working", "timestamp": ts()}})
        result = await handle_task(req.task, req.params)
        yield _sse(result.model_dump())

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
