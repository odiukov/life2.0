from fastapi import FastAPI, HTTPException
from contextlib import asynccontextmanager
from pydantic import BaseModel
import httpx

from .registry import discover_agents, get_agent_url, list_agents
from .router import classify_intent


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


class ChatRequest(BaseModel):
    message: str
    params: dict = {}


@app.post("/chat")
async def chat(req: ChatRequest):
    agent_name = classify_intent(req.message)
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


@app.get("/agents")
async def agents():
    return {"agents": list_agents()}


@app.get("/health")
async def health():
    return {"status": "ok"}
