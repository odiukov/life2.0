from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from contextlib import asynccontextmanager
from pydantic import BaseModel
import httpx
import uuid
import json

from .registry import discover_agents, get_agent_url, list_agents, check_agent_health, get_registry
from .router import classify_intent
from .db import get_stats, get_tasks_today, clear_activity


AGENT_DEFAULT_TASK: dict[str, str] = {
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    await discover_agents()
    yield


app = FastAPI(title="Orchestrator", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatRequest(BaseModel):
    message: str
    params: dict = {}


class StreamChatRequest(BaseModel):
    threadId: str = ""
    runId: str = ""
    messages: list[dict] = []
    actions: list = []
    extensions: dict = {}
    forward_props: dict = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"



@app.post("/chat")
async def chat(req: ChatRequest):
    agent_name = classify_intent(req.message)

    if agent_name == "sync":
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                resp = await client.post("http://sync-service:8080/sync")
                resp.raise_for_status()
                data = resp.json()
                text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
                if data.get("errors"):
                    text += f" Errors: {'; '.join(data['errors'][:3])}"
            return {"output": text}
        except Exception as e:
            raise HTTPException(status_code=503, detail=f"Sync service error: {str(e)}")

    agent_url = get_agent_url(agent_name)
    if not agent_url:
        raise HTTPException(
            status_code=503,
            detail=f"Agent '{agent_name}' is not available. Available: {list_agents()}"
        )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{agent_url}/tasks",
                json={"task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"), "params": {"message": req.message}},
            )
            resp.raise_for_status()
            return resp.json()
        except httpx.HTTPStatusError as e:
            raise HTTPException(
                status_code=e.response.status_code,
                detail=f"Agent '{agent_name}' error: {e.response.text[:500]}",
            )
        except httpx.RequestError as e:
            raise HTTPException(
                status_code=503,
                detail=f"Could not reach agent '{agent_name}': {str(e)}",
            )


@app.post("/chat/stream")
async def chat_stream(req: StreamChatRequest):
    thread_id = req.threadId or str(uuid.uuid4())
    run_id = req.runId or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    user_messages = [m for m in req.messages if m.get("role") == "user"]

    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")

    message = user_messages[-1].get("content", "")

    agent_name = classify_intent(message)

    if agent_name == "sync":
        async def sync_stream():
            yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
            yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
            try:
                async with httpx.AsyncClient(timeout=60.0) as client:
                    resp = await client.post("http://sync-service:8080/sync")
                    resp.raise_for_status()
                    data = resp.json()
                    text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
                    if data.get("errors"):
                        text += f" Errors: {'; '.join(data['errors'][:3])}"
            except Exception as e:
                text = f"Sync failed: {str(e)}"
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": text})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

        return StreamingResponse(
            sync_stream(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    agent_url = get_agent_url(agent_name)

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})

        if not agent_url:
            error_text = f"Agent '{agent_name}' is not available."
            yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": error_text})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})
            return

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                resp = await client.post(
                    f"{agent_url}/tasks",
                    json={"task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"), "params": {"message": message}},
                )
                resp.raise_for_status()
                output = resp.json().get("output", "")
        except Exception as e:
            output = f"Error contacting agent: {str(e)}"

        yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": output})

        yield _sse({"type": "TextMessageEnd", "messageId": message_id})
        yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "X-Accel-Buffering": "no",
        },
    )


@app.get("/stats")
async def stats():
    return await get_stats()


@app.delete("/activity")
async def delete_activity():
    deleted = await clear_activity()
    return {"deleted": deleted}


@app.get("/agents")
async def agents():
    registry = get_registry()
    result = []
    for name, entry in registry.items():
        online = await check_agent_health(name)
        tasks_today = await get_tasks_today(name)
        card = entry.get("card", {})
        result.append({
            "name": name,
            "url": entry["url"],
            "online": online,
            "capabilities": card.get("capabilities", []),
            "description": card.get("description", ""),
            "tasks_today": tasks_today,
        })
    return {"agents": result}


@app.get("/health")
async def health():
    return {"status": "ok"}
