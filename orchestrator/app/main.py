# orchestrator/app/main.py
import json
import uuid
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from copilotkit import CopilotKitRemoteEndpoint
from copilotkit.langgraph_agent import LangGraphAgent as _CopilotKitLangGraphAgent
from copilotkit.integrations.fastapi import add_fastapi_endpoint
from .health_agent import create_health_agent

from .briefing import run_briefing
from .db import clear_activity, get_health_summary, get_stats, get_tasks_today
from .registry import check_agent_health, discover_agents, get_agent_url, get_registry, list_agents
from .router import classify_intent

AGENT_DEFAULT_TASK: dict[str, str] = {
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
}

_SYNC_SERVICE_URL = "http://sync-service:8080/sync"


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


# ---------------------------------------------------------------------------
# CopilotKit SDK — LangGraph agent required by CopilotKit v1.8
# ---------------------------------------------------------------------------

# Workaround for copilotkit 0.1.86 incompatibility:
# - CopilotKitRemoteEndpoint rejects the old LangGraphAgent at init time
# - LangGraphAGUIAgent (new) has broken dict_repr and missing execute()
# Solution: use old LangGraphAgent (has working execute()) but report type
# "langgraph_agui" so CopilotKit v1.8 frontend recognises it. Bypass the
# isinstance check by assigning agents after init.
class _HealthAgent(_CopilotKitLangGraphAgent):
    def dict_repr(self):
        base = super().dict_repr()
        base["type"] = "langgraph_agui"
        return base


_copilotkit_sdk = CopilotKitRemoteEndpoint()
_copilotkit_sdk.agents = [
    _HealthAgent(
        name="default",
        description="Personal health assistant with access to sleep, workout, and nutrition data",
        graph=create_health_agent(),
    )
]

add_fastapi_endpoint(app, _copilotkit_sdk, "/copilotkit")


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


def _build_peer_agents(primary: str) -> dict:
    """Return all registry agents except primary, formatted for A2A peer_agents param."""
    registry = get_registry()
    return {
        name: {"url": entry["url"], "card": entry.get("card", {})}
        for name, entry in registry.items()
        if name != primary
    }


def _artifact_text(data: dict) -> str:
    """Extract text from first A2A artifact, fall back to legacy 'output' field."""
    artifacts = data.get("artifacts", [])
    if artifacts and artifacts[0].get("parts"):
        return artifacts[0]["parts"][0].get("text", "")
    return data.get("output", "")


# Maps peer artifact name prefix to display label
_PEER_LABELS: dict[str, str] = {
    "sleep": "sleep-agent",
    "nutrition": "nutrition-agent",
    "workout": "workout-agent",
}


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
            detail=f"Agent '{agent_name}' is not available. Available: {list_agents()}",
        )

    async with httpx.AsyncClient(timeout=180.0) as client:
        try:
            resp = await client.post(
                f"{agent_url}/tasks",
                json={
                    "id": str(uuid.uuid4()),
                    "task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"),
                    "params": {"message": req.message, "peer_agents": _build_peer_agents(agent_name)},
                },
            )
            resp.raise_for_status()
            return {"output": _artifact_text(resp.json())}
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
            yield _sse({"type": "TextMessageContent", "messageId": message_id,
                        "delta": f"Agent '{agent_name}' is not available."})
            yield _sse({"type": "TextMessageEnd", "messageId": message_id})
            yield _sse({"type": "RunFinished", "threadId": thread_id, "runId": run_id})
            return

        try:
            async with httpx.AsyncClient(timeout=180.0) as client:
                async with client.stream(
                    "POST",
                    f"{agent_url}/tasks/stream",
                    json={
                        "id": str(uuid.uuid4()),
                        "task": AGENT_DEFAULT_TASK.get(agent_name, f"analyze_{agent_name}"),
                        "params": {"message": message, "peer_agents": _build_peer_agents(agent_name)},
                    },
                ) as resp:
                    resp.raise_for_status()
                    async for line in resp.aiter_lines():
                        if not line.startswith("data: "):
                            continue
                        event = json.loads(line[6:])
                        state = event.get("status", {}).get("state")
                        artifacts = event.get("artifacts", [])

                        for artifact in artifacts:
                            name = artifact.get("name", "")
                            parts = artifact.get("parts", [])
                            text = parts[0].get("text", "") if parts else ""
                            if not text:
                                continue

                            if name.startswith("peer_"):
                                # Show live agent consultation status in chat
                                peer_key = name[5:]  # strip "peer_"
                                label = _PEER_LABELS.get(peer_key, peer_key)
                                delta = f"\n\n*Консультирую {label}...*\n\n{text}"
                                yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": delta})
                            elif state == "completed":
                                yield _sse({"type": "TextMessageContent", "messageId": message_id, "delta": text})
                            elif state == "failed":
                                yield _sse({"type": "TextMessageContent", "messageId": message_id,
                                            "delta": f"Agent error: {text}"})

        except Exception as e:
            yield _sse({"type": "TextMessageContent", "messageId": message_id,
                        "delta": f"Error contacting agent: {str(e)}"})

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
    result = await run_briefing(get_registry(), use_today=debug)
    return result


@app.get("/health")
async def health():
    return {"status": "ok"}
