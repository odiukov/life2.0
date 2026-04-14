"""Orchestrator HTTP entrypoint."""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage
from pydantic import BaseModel

from .briefing import run_briefing
from .db import clear_activity, get_health_summary, get_stats, get_tasks_today
from .health_agent import create_health_agent
from .registry import check_agent_health, discover_agents, get_registry


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

_graph = create_health_agent()

add_langgraph_fastapi_endpoint(
    app,
    LangGraphAgent(
        name="default",
        description="Personal health assistant with access to sleep, workout, and nutrition agents",
        graph=_graph,
    ),
    path="/agui",
)


class StreamChatRequest(BaseModel):
    threadId: str = ""
    runId: str = ""
    messages: list[dict] = []
    actions: list = []
    extensions: dict = {}
    forward_props: dict = {}


def _sse(event: dict) -> str:
    return f"data: {json.dumps(event)}\n\n"


@app.post("/chat/stream")
async def chat_stream(req: StreamChatRequest):
    thread_id = req.threadId or str(uuid.uuid4())
    run_id = req.runId or str(uuid.uuid4())
    message_id = str(uuid.uuid4())

    user_messages = [m for m in req.messages if m.get("role") == "user"]
    if not user_messages:
        raise HTTPException(status_code=400, detail="No user message found")
    text = user_messages[-1].get("content", "")

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
        try:
            async for event in _graph.astream(
                {"messages": [HumanMessage(content=text)]},
                config={"configurable": {"thread_id": thread_id}},
            ):
                for _node, update in event.items():
                    messages = update.get("messages") if isinstance(update, dict) else None
                    if not messages:
                        continue
                    last = messages[-1]
                    content = getattr(last, "content", "")
                    if content:
                        yield _sse({
                            "type": "TextMessageContent",
                            "messageId": message_id,
                            "delta": content,
                        })
        except Exception as e:
            yield _sse({
                "type": "TextMessageContent",
                "messageId": message_id,
                "delta": f"Error: {e}",
            })

        yield _sse({"type": "TextMessageEnd", "messageId": message_id})
        yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@app.get("/stats")
async def stats():
    return await get_stats()


@app.get("/health-summary")
async def health_summary():
    return await get_health_summary()


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
            "capabilities": card.get("capabilities", {}),
            "description": card.get("description", ""),
            "tasks_today": tasks_today,
        })
    return {"agents": result}


@app.post("/briefing")
async def briefing(debug: bool = False):
    return await run_briefing(get_registry(), use_today=debug)


@app.get("/health")
async def health():
    return {"status": "ok"}
