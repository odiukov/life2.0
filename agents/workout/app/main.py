# agents/workout/app/main.py
import json
import logging
import uuid
from datetime import datetime, timezone

import httpx
from fastapi import BackgroundTasks, FastAPI
from fastapi.responses import StreamingResponse

from shared.a2a import A2ATaskRequest
from .agent_card import AGENT_CARD
from .tasks import fetch_peer_artifacts, handle_task

app = FastAPI(title="Workout Agent")

logger = logging.getLogger(__name__)


def _sse(event: dict, event_type: str = "message") -> str:
    return f"event: {event_type}\ndata: {json.dumps(event)}\n\n"


async def _send_webhook(url: str, payload: dict) -> None:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            await client.post(url, json=payload)
    except Exception as e:
        logger.warning("Webhook delivery failed to %s: %s", url, e)


@app.get("/.well-known/agent.json")
async def agent_card():
    return AGENT_CARD


@app.post("/tasks")
async def create_task(req: A2ATaskRequest, background_tasks: BackgroundTasks):
    result = await handle_task(req.task, req.params)
    if req.params.get("webhook_url"):
        background_tasks.add_task(_send_webhook, req.params["webhook_url"], result.model_dump())
    return result


@app.post("/tasks/stream")
async def stream_task(req: A2ATaskRequest, background_tasks: BackgroundTasks):
    task_id = req.id or str(uuid.uuid4())
    peer_agents = req.params.get("peer_agents", {})

    async def generate():
        ts = lambda: datetime.now(timezone.utc).isoformat()
        yield _sse({"id": task_id, "status": {"state": "submitted", "timestamp": ts()}}, "task-status-update")
        yield _sse({"id": task_id, "status": {"state": "working", "timestamp": ts()}}, "task-status-update")

        # Fetch peer artifacts and stream each one as it arrives
        peer_artifacts = await fetch_peer_artifacts(peer_agents)
        for name, text in peer_artifacts.items():
            yield _sse(
                {
                    "id": task_id,
                    "status": {"state": "working", "timestamp": ts()},
                    "artifacts": [{"name": f"peer_{name}", "parts": [{"type": "text", "text": text}]}],
                },
                "task-status-update",
            )

        # Pass pre-fetched artifacts to avoid double peer calls
        result = await handle_task(req.task, req.params, peer_artifacts=peer_artifacts)
        result.id = task_id  # consistent ID
        yield _sse(result.model_dump(), "task-artifact-update")

    return StreamingResponse(
        generate(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/health")
async def health():
    return {"status": "ok"}
