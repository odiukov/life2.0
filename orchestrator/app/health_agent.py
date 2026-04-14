# orchestrator/app/health_agent.py
import uuid
import warnings

import httpx
from langchain_core.tools import tool

from .llm import build_llm

_AGENT_DEFAULT_TASK: dict[str, str] = {
    "sleep": "analyze_sleep",
    "workout": "analyze_workout",
    "nutrition": "analyze_nutrition",
}

_SYNC_SERVICE_URL = "http://sync-service:8080/sync"


def _get_peer_agents(primary: str) -> dict:
    from .registry import get_registry
    registry = get_registry()
    return {
        name: {"url": entry["url"], "card": entry.get("card", {})}
        for name, entry in registry.items()
        if name != primary
    }


def _extract_text(data: dict) -> str:
    artifacts = data.get("artifacts", [])
    if artifacts and artifacts[0].get("parts"):
        return artifacts[0]["parts"][0].get("text", "")
    return data.get("output", "")


async def _call_agent(agent: str, message: str) -> str:
    from .registry import get_agent_url
    agent_url = get_agent_url(agent)
    if not agent_url:
        return f"Agent '{agent}' is currently unavailable."
    try:
        async with httpx.AsyncClient(timeout=180.0) as client:
            resp = await client.post(
                f"{agent_url}/tasks",
                json={
                    "id": str(uuid.uuid4()),
                    "task": _AGENT_DEFAULT_TASK.get(agent, f"analyze_{agent}"),
                    "params": {"message": message, "peer_agents": _get_peer_agents(agent)},
                },
            )
            resp.raise_for_status()
            return _extract_text(resp.json())
    except httpx.HTTPStatusError as e:
        return f"Agent '{agent}' error {e.response.status_code}: {e.response.text[:200]}"
    except httpx.RequestError as e:
        return f"Could not reach agent '{agent}': {str(e)}"
    except Exception as e:
        return f"Error calling {agent} agent: {str(e)}"


@tool
async def analyze_sleep(message: str) -> str:
    """Analyze sleep patterns, quality, and recovery data.
    Use for questions about sleep duration, HRV, deep sleep, REM, sleep score, etc."""
    return await _call_agent("sleep", message)


@tool
async def analyze_workout(message: str) -> str:
    """Analyze workout data, exercise performance, and fitness trends.
    Use for questions about activities, steps, calories burned, training load, etc."""
    return await _call_agent("workout", message)


@tool
async def analyze_nutrition(message: str) -> str:
    """Analyze nutrition data, diet quality, and calorie intake.
    Use for questions about food, macros, calories consumed, meal patterns, etc."""
    return await _call_agent("nutrition", message)


@tool
async def sync_health_data() -> str:
    """Synchronize health data from Garmin and Yazio to get the latest metrics."""
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(_SYNC_SERVICE_URL)
            resp.raise_for_status()
            data = resp.json()
            text = f"Sync complete: {data['synced']} records synced, {data['skipped']} skipped."
            if data.get("errors"):
                text += f" Errors: {'; '.join(data['errors'][:3])}"
            return text
    except Exception as e:
        return f"Sync failed: {str(e)}"


@tool
async def send_daily_briefing() -> str:
    """Generate and send the daily health briefing to the user via Telegram."""
    from .registry import get_registry
    from .briefing import run_briefing
    try:
        await run_briefing(get_registry())
        return "Daily health briefing generated and sent via Telegram."
    except Exception as e:
        return f"Briefing failed: {str(e)}"


_SYSTEM_PROMPT = (
    "You are a personal health assistant. You have access to specialized agents "
    "for sleep, workout, and nutrition analysis.\n\n"
    "When asked about health data, ALWAYS call the relevant tool first:\n"
    "- Sleep questions → analyze_sleep\n"
    "- Workout/exercise questions → analyze_workout\n"
    "- Nutrition/food/diet questions → analyze_nutrition\n"
    "- Synchronize data → sync_health_data\n"
    "- Daily briefing → send_daily_briefing\n\n"
    "Be concise and actionable. Present data clearly."
)


def create_health_agent():
    """Create the LangGraph ReAct agent for health analysis."""
    from langgraph.checkpoint.memory import MemorySaver
    llm = build_llm()
    tools = [analyze_sleep, analyze_workout, analyze_nutrition, sync_health_data, send_daily_briefing]

    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        from langgraph.prebuilt import create_react_agent
        return create_react_agent(llm, tools, prompt=_SYSTEM_PROMPT, checkpointer=MemorySaver())
