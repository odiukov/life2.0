"""Orchestrator HTTP entrypoint."""
from __future__ import annotations

import json
import uuid
from contextlib import asynccontextmanager

from ag_ui_langgraph import LangGraphAgent, add_langgraph_fastapi_endpoint
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import PlainTextResponse, StreamingResponse
from langchain_core.messages import AIMessage, HumanMessage
from pydantic import BaseModel

from .briefing import build_dashboard, run_briefing
from .db import clear_activity, get_health_summary, get_stats, get_tasks_today, get_yesterday_metrics
from .health_agent import create_health_agent
from .registry import check_agent_health, discover_agents, get_registry


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _graph, _pool, _saver
    from .checkpointer import close_checkpointer, open_checkpointer
    await discover_agents()
    _pool, _saver = await open_checkpointer()
    _graph = await create_health_agent(checkpointer=_saver)
    # Late-register the AG-UI endpoint now that _graph exists.
    add_langgraph_fastapi_endpoint(
        app,
        LangGraphAgent(
            name="default",
            description="Personal health assistant with access to sleep, workout, nutrition, body, mood, habits agents plus live Google Calendar tools",
            graph=_graph,
        ),
        path="/agui",
    )
    try:
        yield
    finally:
        from .mcp_tools import close_mcp_sessions
        await close_mcp_sessions()
        if _pool is not None:
            await close_checkpointer(_pool)


# Populated by lifespan; must exist at module level so endpoint functions can close over them.
_graph = None
_pool = None
_saver = None

app = FastAPI(title="Orchestrator", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000"],
    allow_methods=["*"],
    allow_headers=["*"],
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

    async def _run_graph():
        async for event in _graph.astream(
            {"messages": [HumanMessage(content=text)]},
            config={"configurable": {"thread_id": thread_id}},
        ):
            for _node, update in event.items():
                messages = update.get("messages") if isinstance(update, dict) else None
                if not messages:
                    continue
                last = messages[-1]
                if not isinstance(last, AIMessage) or getattr(last, "tool_calls", None):
                    continue
                content = getattr(last, "content", "")
                if content:
                    yield content

    async def event_stream():
        yield _sse({"type": "RunStarted", "threadId": thread_id, "runId": run_id})
        yield _sse({"type": "TextMessageStart", "messageId": message_id, "role": "assistant"})
        tried_reset = False
        while True:
            try:
                async for content in _run_graph():
                    yield _sse({
                        "type": "TextMessageContent",
                        "messageId": message_id,
                        "delta": content,
                    })
                break
            except ValueError as e:
                # LangGraph raises ValueError with "INVALID_CHAT_HISTORY" when the stored
                # checkpoint has AIMessage tool_calls without matching ToolMessages — e.g.
                # after an interrupted run. Wipe the thread and retry once.
                if "INVALID_CHAT_HISTORY" in str(e) and not tried_reset and _saver is not None:
                    tried_reset = True
                    try:
                        await _saver.adelete_thread(thread_id)
                    except Exception as del_err:
                        yield _sse({
                            "type": "TextMessageContent",
                            "messageId": message_id,
                            "delta": f"Error: {del_err}",
                        })
                        break
                    yield _sse({
                        "type": "TextMessageContent",
                        "messageId": message_id,
                        "delta": "♻️ Предыдущий разговор был прерван, начинаю заново.\n\n",
                    })
                    continue
                yield _sse({
                    "type": "TextMessageContent",
                    "messageId": message_id,
                    "delta": f"Error: {e}",
                })
                break
            except Exception as e:
                yield _sse({
                    "type": "TextMessageContent",
                    "messageId": message_id,
                    "delta": f"Error: {e}",
                })
                break

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
        skills_raw = card.get("skills") or []
        skills = [
            {"id": s.get("id", ""), "name": s.get("name", s.get("id", ""))}
            for s in skills_raw
        ]
        result.append({
            "name": name,
            "url": entry["url"],
            "online": online,
            "skills": skills,
            "description": card.get("description", ""),
            "tasks_today": tasks_today,
        })
    return {"agents": result}


@app.post("/briefing")
async def briefing(debug: bool = False):
    return await run_briefing(get_registry(), use_today=debug)


@app.get("/dashboard", response_class=PlainTextResponse)
async def dashboard_endpoint():
    metrics = await get_yesterday_metrics()
    return build_dashboard(metrics, insight=None)


@app.get("/health")
async def health():
    return {"status": "ok"}
